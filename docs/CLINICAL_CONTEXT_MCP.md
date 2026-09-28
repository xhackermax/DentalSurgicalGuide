# DSG Clinical Context MCP

## Goal

DSG stores structured patient medical context and gives MCP enough context to research the
*current* medication and oral-surgical guidance applicable to the patient's country.  The
addon does not freeze changing clinical recommendations into Blender code.

## Workflow

1. Dentist enters country, age, medications, relevant diseases and laboratory results.
2. DSG normalizes the data and creates a context SHA-256.
3. MCP calls `build_clinical_guidance_request` or `build_preoperative_context`.
4. The request identifies missing data, medication-reconciliation needs, guidance topics,
   country-specific source priorities and the exact request SHA-256.
5. MCP performs live research from authoritative sources, starting with local official
   medication/regulatory and professional guidance.
6. MCP returns `dsg.clinical_guidance_result.v1` with source IDs and citations/URLs.
7. DSG validates that the result matches the exact current request and stores it.
8. The dentist reviews the sourced result in Blender. Review confirmation is deliberately
   not exposed to MCP.

## Spain adapter

For Spain, medication reconciliation should prefer AEMPS CIMA.  The bundled request
includes the official REST base and endpoint descriptors.  DSG itself does not perform
network requests on Blender's main thread.

Priority clinical sources bundled for discovery:

- AEMPS CIMA: medicine authorization, active ingredients, route/dose, technical sheets,
  safety notes and product status.
- SECOMCyC: oral and maxillofacial professional documents/protocols.
- SEPA: dental/implant periodontal guidance including the 2025 multidisciplinary MRONJ
  position resource.
- Consejo General de Dentistas de España.
- Ministerio de Sanidad.

## Other countries

Country source definitions are data-only entries in `resources/clinical/source_registry.json`.
GB and US examples are bundled.  If a country is not registered, DSG marks
`country_source_discovery_required=true`, and MCP must first discover and verify:

- official medicine regulator,
- national dental professional body,
- oral/maxillofacial society,
- national clinical guidance,
- then international consensus as fallback.

This lets the system support any country without pretending a static bundled list is
complete forever.

## Clinical result contract

A returned result must include:

- `schema = dsg.clinical_guidance_result.v1`
- exact `request_sha256`
- `country_code`
- `verified_at`
- at least one source with unique ID, publisher and URL
- each guidance/risk/recommendation statement must cite at least one source ID
- explicit source conflicts when guidance disagrees
- `requires_clinician_review`
- optional `requires_medical_consultation`

DSG validates traceability, not medical truth.  MCP remains responsible for using current
sources and accurately representing them.

## Privacy boundary

The clinical schema has no patient name, address, record number or similar identifier.
Clinical data are stored in the `.blend` file and should therefore be handled as sensitive
health information.  Do not enter direct identifiers into free-text notes.
