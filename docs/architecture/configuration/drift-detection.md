# Configuration Drift Detection — Future Architecture

Drift detection compares **approved desired state** against normalized observed state, independent of one-off compliance rules. It is future scope, not a deployed datastore or background watcher.

```text
Approved desired state (versioned, scoped)
             + current observed facts
                    -> semantic comparison
                    -> match | drift | unknown/unsupported
                    -> finding
                    -> proposed Change Plan
                    -> explicit approval and controlled execution
```

Record provenance, target, scope, baseline version, relevant normalized fields, observation timestamp and confidence/unsupported fields. Ignore irrelevant transient data and normalize vendor representation through owning observation/audit layers. Distinguish intentional exceptions from unauthorized deviation.

Never automatically apply drift remediation. Unknown or incomplete observations must not be treated as drift or trigger change. Design a separate change-ownership policy for manual updates so the desired baseline is not silently overwritten after deployment. Schedule, persistence and UI require separately approved implementation tasks.
