# Capstone demonstration

1. Sign in with your locally generated administrator credentials.
2. Note the Demo mode banner.
3. Click Run scan. Wait for Scan completed.
4. Overview shows costs, estimated savings, four resources and three finding types.
5. Open Resources, inspect the RDS database and missing-metrics instance.
6. Open the idle EC2 recommendation. Explain its observation window and maximum metrics.
7. Approve, then simulate execution. Confirm the exact resource in the dialog.
8. Show execution history: simulated=true, no AWS request occurred.
9. Open RDS recommendation: explain why it is advisory and savings are unavailable.
10. Open the cost anomaly: compare completed-day spend with its fourteen-day baseline.
11. Settings: validate the demo connection and save collection preferences.
12. Explain optional AWS/Claude/Slack integrations and which have been configured.
13. Refresh/restart: database records persist.
14. Show tests and the module ownership in the README.

Evaluation: evidence sufficiency, valid savings arithmetic, approval enforcement,
duplicate execution protection, missing-data handling, and honest provenance.

Known scope: no multi-account/multi-cloud support, no autonomous database resizing,
no production cost guarantee or confirmed realized savings.
