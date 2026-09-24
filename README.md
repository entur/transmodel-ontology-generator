# Transmodel v6.2 TTL generator

Small private repository containing only the generator and its generated Turtle output.

The generator uses the official public Transmodel v6.2 Enterprise Architect extract:

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
