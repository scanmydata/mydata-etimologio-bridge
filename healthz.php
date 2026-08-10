<?php
// Liveness probe for the container/orchestrator. Deliberately dependency-free:
// it must answer even when the database or the ΑΑΔΕ are unreachable, otherwise a
// transient upstream outage would make the platform restart a healthy app.
header('Content-Type: text/plain; charset=utf-8');
echo 'ok';
