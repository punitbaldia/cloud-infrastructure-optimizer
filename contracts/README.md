# Initial team contract

Person 2 owns these schemas. Discuss changes before changing field names.
Generated OpenAPI and JSON schemas are exported by backend/export_contracts.py.

- API: http://localhost:8000/api/v1; docs: http://localhost:8000/docs
- List responses: {items: [...], total, limit, offset, data_source: "mock"}.
- Internal record IDs are UUID strings. Resource.resource_id is the cloud/provider ID;
  Resource.id is the database UUID used by GET /resources/{id}.
- Monetary values are decimal strings or null, with explicit currency.
- Error envelope: {error: {code, message, details}}.
- Scan and execution creation return 202; poll by returned id.
- Approval/dismissal require no body. Execution requires a UUID idempotency_key.
- Each recommendation can produce only one execution job in this milestone.
- Advisory findings cannot be approved/executed.
- All resources and costs currently have mock provenance; execution always simulated.
- UTC timestamps use offsets or Z; clients should accept both.
- Empty state is expected until POST /scans is called.
- No authentication yet; local use only.

## Person 1

Do not replace database or API files. Person 2's temporary adapter is
backend/app/services/mock_provider.py. Your real package can expose:

collect_snapshots(connection, start, end) -> list[ResourceSnapshot or compatible dict]
collect_daily_costs(connection, start, end) -> list[DailyCost or compatible dict]

Datetimes passed to adapters are timezone-aware UTC. Connection is {} in this mock
milestone; connection onboarding is not implemented. ADAPTER_MODULE can select an
importable adapter for integration testing. Do not use it for live data yet: provenance
and account connection handling must be extended first.

Metric keys for the current EC2 rule:
cpu_percent: Percent, maximum, at least 168 samples
network_bytes_per_hour: Bytes/hour, maximum, at least 168 samples
Never relabel CloudWatch raw byte metrics without the appropriate aggregation/unit
conversion. Demo prices belong only in the temporary fixture.

Your remediation package will be connected separately after policy review.
Current backend always invokes its local simulator.

## Person 3

Use generated openapi.json and examples.json. Start with POST /scans and the
recommendation list. All controls must show simulation mode. RDS has inventory but no
rightsizing recommendation in this milestone. Overview costs are fixture coverage only.
Do not display simulated completion as observed savings. No settings/login screens
should claim real backend integration yet.

