#!/bin/bash
# Run inside a fresh task directory, normally on a PBS compute node.
set -euo pipefail
result=$(awk 'BEGIN { total=0; for(i=1;i<=100000;i++) total+=i; printf "%.0f",total }')
test "$result" = 5000050000
printf 'sum_1_to_100000=%s\n' "$result" > result.txt.tmp
mv result.txt.tmp result.txt
printf 'COMPLETE\n' > status.tmp
mv status.tmp status
printf 'job_id=%s\n' "${PBS_JOBID:-local-check}"
printf 'compute_host='; hostname
cat result.txt status
