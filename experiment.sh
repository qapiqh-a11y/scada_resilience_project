#!/usr/bin/env sh
set -eu

mode="${1:-off}"
case "$mode" in
  off|on) ;;
  *) echo "usage: $0 off|on" >&2; exit 2 ;;
esac

duration_s="${DURATION_S:-120}"
rate_rps="${RATE_RPS:-20}"
mkdir -p results

kubectl create configmap scada-code \
  --from-file=core.py \
  --from-file=server.py \
  --from-file=dep.py \
  --from-file=loadgen.py \
  --from-file=metrics.py \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap scada-run-settings \
  --from-literal=mode="$mode" \
  --from-literal=duration_s="$duration_s" \
  --from-literal=rate_rps="$rate_rps" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f stand.yaml
kubectl set env deployment/scada-core PATTERN="$mode"
kubectl rollout status deployment/scada-dep --timeout=90s
kubectl rollout status deployment/scada-core --timeout=90s

kubectl delete job scada-load --ignore-not-found
kubectl apply -f load-job.yaml

sleep 30
kubectl exec deployment/scada-dep -- sh -c \
  'printf "%s" "{\"delay_ms\":2000}" > /tmp/scada/fault.json'
sleep 30
kubectl exec deployment/scada-dep -- sh -c \
  'printf "%s" "{}" > /tmp/scada/fault.json'

kubectl wait --for=condition=complete job/scada-load --timeout=180s
pod="$(kubectl get pods -l job-name=scada-load -o jsonpath='{.items[0].metadata.name}')"
kubectl cp "$pod:/results/$mode.csv" "results/$mode.csv"
kubectl logs "$pod" > "results/$mode.log"
python3 metrics.py "results/$mode.csv" | tee -a "results/$mode.log"

echo "saved results/$mode.csv and results/$mode.log"
