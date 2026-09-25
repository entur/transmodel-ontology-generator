# Transmodel ontology generator

Small repository containing only the generator and its generated Turtle output for the
Transmodel v6.2 base ontology. It mirrors the split used for
[`nordic-netex-ontology`](https://github.com/entur/nordic-netex-ontology) and
[`nordic-siri-ontology`](https://github.com/entur/nordic-siri-ontology): the generated base
stays a faithful, mechanical projection of the official CEN model, kept separate from any
profile or alignment layer.

The generator uses the official public Transmodel v6.2 Enterprise Architect extract, licensed
as open data by CEN:

https://transmodel-cen.eu/model6.2/Transmodel2024-EA_extract_for_publication.xml

## Generate

Install the only runtime dependency:

```powershell
python -m pip install rdflib
```

Generate the output:

```powershell
python generate_transmodel_ttl.py Transmodel2024-EA_extract_for_publication.xml transmodel-v6.2.ttl
```

The v6.2 XMI extract has very sparse class-level documentation, so most concepts have no
`skos:definition` yet. This generator is scoped to v6.2 only; it does not pull in v6.0
material.

The source XML is intentionally not committed. The generated TTL preserves:

- UML concepts and types
- labels and documentation where present
- full package paths
- stable `tm:module` provenance
- attributes and multiplicities
- generalizations
- associations and association ends
- XMI identifiers

The aggregate `transmodel-v6.2.ttl` is the canonical output. Modules can be filtered later using `tm:module` or `tm:packagePath`.
