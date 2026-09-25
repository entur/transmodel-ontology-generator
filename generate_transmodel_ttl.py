from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

XMI = "http://www.omg.org/spec/XMI/20131001"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
TM = Namespace("https://w3id.org/transmodel/")


def attr(element: ET.Element, name: str) -> str | None:
    return element.get(name) or element.get(f"{{{XMI}}}{name}") or element.get(f"{{{XSI}}}{name}")


def local_type(value: str | None) -> str | None:
    return value.split(":")[-1] if value else None


def clean(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    return value or None


def child_value(element: ET.Element, name: str) -> str | None:
    child = element.find(name)
    return clean(child.get("value") or child.text) if child is not None else None


def module_name(package: tuple[str, ...]) -> str:
    value = package[1] if len(package) > 1 else (package[0] if package else "unpackaged")
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "unpackaged"


def documentation(element: ET.Element, by_id: dict[str, str]) -> str | None:
    parts = []
    element_id = attr(element, "id")
    if element_id in by_id:
        parts.append(by_id[element_id])
    for node in element.iter("documentation"):
        text = clean(node.get("value") or "".join(node.itertext()))
        if text:
            parts.append(text)
    return " ".join(dict.fromkeys(parts)) or None


def walk(element: ET.Element, packages: tuple[str, ...], concepts: list[dict], relations: list[dict], docs: dict[str, str]) -> None:
    for child in element:
        if child.tag != "packagedElement":
            walk(child, packages, concepts, relations, docs)
            continue
        kind = local_type(attr(child, "type")) or ""
        name = (child.get("name") or "").strip().lstrip(": ").strip()
        if kind == "Package":
            walk(child, packages + ((name,) if name else ()), concepts, relations, docs)
            continue
        if name and kind in {"Class", "DataType", "Enumeration", "PrimitiveType", "AssociationClass", "Signal"}:
            xmi_id = attr(child, "id") or ""
            concept = {
                "id": f"tm:xmi/{xmi_id}" if xmi_id else f"tm:term/{name}",
                "label": name,
                "kind": kind,
                "xmiId": xmi_id,
                "package": list(packages),
                "module": module_name(packages),
                "definition": documentation(child, docs),
                "attributes": [],
                "generalizations": [],
            }
            for attribute in child.findall("ownedAttribute"):
                attribute_name = (attribute.get("name") or "").strip()
                if not attribute_name:
                    continue
                concept["attributes"].append({
                    "name": attribute_name,
                    "xmiId": attr(attribute, "id"),
                    "type": local_type(attribute.get("type")),
                    "lower": child_value(attribute, "lowerValue"),
                    "upper": child_value(attribute, "upperValue"),
                    "definition": documentation(attribute, docs),
                    "aggregation": attribute.get("aggregation"),
                })
            for generalization in child.findall("generalization"):
                parent = generalization.get("general")
                if parent:
                    concept["generalizations"].append(parent)
                    relations.append({
                        "id": f"tm:xmi/generalization/{attr(generalization, 'id') or len(relations)}",
                        "type": "tm:Relation",
                        "subject": concept["id"],
                        "predicate": RDFS.subClassOf,
                        "objectXmiId": parent,
                        "relationType": "uml-generalization",
                        "module": module_name(packages),
                    })
            concepts.append(concept)
        if kind == "Association" and name:
            ends = []
            for end in child.findall("ownedEnd"):
                ends.append({
                    "name": end.get("name"),
                    "xmiId": attr(end, "id"),
                    "typeXmiId": end.get("type"),
                    "lower": child_value(end, "lowerValue"),
                    "upper": child_value(end, "upperValue"),
                    "aggregation": end.get("aggregation"),
                    "definition": documentation(end, docs),
                })
            relations.append({
                "id": f"tm:xmi/association/{attr(child, 'id') or name}",
                "type": "tm:Relation",
                "label": name,
                "kind": "Association",
                "xmiId": attr(child, "id"),
                "package": list(packages),
                "module": module_name(packages),
                "ends": ends,
                "definition": documentation(child, docs),
                "relationType": "uml-association",
            })
        walk(child, packages, concepts, relations, docs)


def literal(graph: Graph, subject: URIRef, predicate: URIRef, value: object) -> None:
    if value is not None and value != "":
        graph.add((subject, predicate, Literal(value)))


def generate(source: Path, output: Path) -> None:
    root = ET.parse(source).getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    docs = {}
    for node in root.iter("documentation"):
        parent = parents.get(node)
        text = clean(node.get("value") or "".join(node.itertext()))
        reference = parent.get(f"{{{XMI}}}idref") if parent is not None else None
        if reference and text:
            docs.setdefault(reference, text)
    concepts: list[dict] = []
    relations: list[dict] = []
    walk(root, (), concepts, relations, docs)
    by_xmi = {item["xmiId"]: item["id"] for item in concepts if item.get("xmiId")}
    for relation in relations:
        object_id = relation.pop("objectXmiId", None)
        if object_id:
            relation["object"] = by_xmi.get(object_id, f"tm:xmi/{object_id}")
        for end in relation.get("ends", []):
            type_id = end.pop("typeXmiId", None)
            end["type"] = by_xmi.get(type_id, f"tm:xmi/{type_id}") if type_id else None
    graph = Graph()
    graph.bind("tm", TM); graph.bind("rdfs", RDFS); graph.bind("owl", OWL); graph.bind("skos", SKOS)
    ontology = TM["catalog/transmodel-6.2"]
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal("Transmodel v6.2 catalogue")))
    graph.add((ontology, TM.source, Literal("https://transmodel-cen.eu/model6.2/Transmodel2024-EA_extract_for_publication.xml")))
    graph.add((ontology, TM.version, Literal("6.2")))
    for concept in concepts:
        subject = URIRef(concept["id"])
        graph.add((subject, RDF.type, TM[concept["kind"]]))
        literal(graph, subject, RDFS.label, concept["label"])
        literal(graph, subject, SKOS.definition, concept.get("definition"))
        literal(graph, subject, TM.xmiId, concept.get("xmiId"))
        literal(graph, subject, TM.module, concept.get("module"))
        literal(graph, subject, TM.packagePath, " / ".join(concept.get("package", [])))
        for generalization in concept.get("generalizations", []):
            parent = URIRef(by_xmi.get(generalization, f"tm:xmi/{generalization}"))
            graph.add((subject, RDFS.subClassOf, parent))
        for attribute in concept.get("attributes", []):
            attribute_node = URIRef(f"{subject}/attribute/{attribute.get('xmiId') or attribute.get('name')}")
            graph.add((subject, TM["attribute"], attribute_node))
            literal(graph, attribute_node, RDFS.label, attribute.get("name"))
            literal(graph, attribute_node, TM["type"], attribute.get("type"))
            literal(graph, attribute_node, TM["lower"], attribute.get("lower"))
            literal(graph, attribute_node, TM["upper"], attribute.get("upper"))
            literal(graph, attribute_node, SKOS.definition, attribute.get("definition"))
            literal(graph, attribute_node, TM["aggregation"], attribute.get("aggregation"))
    for relation in relations:
        subject = URIRef(relation["id"])
        graph.add((subject, RDF.type, TM.Relation))
        literal(graph, subject, RDFS.label, relation.get("label"))
        literal(graph, subject, TM.module, relation.get("module"))
        literal(graph, subject, TM.relationType, relation.get("relationType"))
        if relation.get("subject"):
            graph.add((subject, TM.subject, URIRef(relation["subject"])))
        if relation.get("object"):
            graph.add((subject, TM.object, URIRef(relation["object"])))
        predicate = relation.get("predicate")
        if predicate:
            graph.add((subject, TM.predicate, URIRef(str(predicate))))
        for end in relation.get("ends", []):
            end_node = URIRef(f"{subject}/end/{end.get('xmiId') or end.get('name')}")
            graph.add((subject, TM.end, end_node))
            literal(graph, end_node, RDFS.label, end.get("name"))
            if end.get("type"):
                 graph.add((end_node, TM["type"], URIRef(end["type"])))
            literal(graph, end_node, TM["lower"], end.get("lower"))
            literal(graph, end_node, TM["upper"], end.get("upper"))
            literal(graph, end_node, TM["aggregation"], end.get("aggregation"))
    output.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output, format="turtle")
    print(f"generated {len(graph)} triples from {len(concepts)} concepts and {len(relations)} relations")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.source, args.output)
