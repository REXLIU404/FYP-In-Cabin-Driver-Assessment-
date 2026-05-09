# Prepared Session Dataset

This folder is the prototype input source for the runtime monitoring flow.
It is not an ad hoc output fixture.

The intended pipeline is:

```text
Prepared session folder
-> Input Source Adapter
-> Monitoring window construction
-> AI layer inference
-> Late fusion
-> RiskScore / RiskLevel
-> Dashboard + Session Log
```

For this frontend MVP, `telemetry.csv` is parsed by the prepared-session adapter.
The adapter builds ordered windows and applies deterministic prototype inference
so the dashboard can demonstrate the same runtime contract that the FYP2 backend
will later serve from real MobileNetV3 and XGBoost models.
