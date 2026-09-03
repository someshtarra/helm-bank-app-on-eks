# Bank Application on AWS EKS — Production Troubleshooting & Runbook

> **Role & Persona**: Lead Site Reliability Engineer (SRE) & Incident Commander  
> **Audience**: On-Call DevOps Engineers, SREs, and Platform Administrators  
> **Scope**: Diagnostic Runbooks, Root Cause Analyses (RCA), and Remediation Steps

---

## Triage Quick Reference Matrix

| Symptom / Error | Primary Subsystem | Probable Root Cause | Immediate Diagnostic Command |
| :--- | :--- | :--- | :--- |
| **`Multi-Attach error for volume`** | AWS EBS Storage / PVC | EBS RWO volume mounted by multiple pods on distinct EC2 nodes | `kubectl describe pod <pod-name> -n <ns>` |
| **`HPA showing <unknown> / 50%`** | Autoscaling / Metrics Server | Missing CPU requests or Metrics Server not reachable | `kubectl get hpa,pods -n <ns> -o wide` |
| **`CrashLoopBackOff (Exit 137)`** | Resource Limits | Memory limit exceeded (`OOMKilled`) | `kubectl describe pod <pod> \| grep -A 3 Last\ State` |
| **`CrashLoopBackOff (Probes)`** | Health Probes | Startup or liveness probe failing repeatedly | `kubectl get events --field-selector reason=Unhealthy` |
| **`No Endpoints in Service`** | Service Discovery | Selector label mismatch or readiness probe failure | `kubectl get endpoints <service-name> -n <ns>` |
| **`RBAC 403 Forbidden`** | Security / RBAC | ServiceAccount lacks permissions in target namespace | `kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<ns>:<sa>` |

---

## 1. Incident 1: Multi-Attach Volume Error (AWS EBS RWO)

### 1.1 Symptoms
* Pod remains in `ContainerCreating` or `Pending` for >5 minutes.
* `kubectl get pods -n <ns>` displays `Pending` or `FailedMount`.
* `kubectl describe pod <pod>` shows:
  ```text
  Events:
    Warning  FailedAttachVolume  2m   attachdetach-controller
    Multi-Attach error for volume "pvc-5c8e312a-..." Volume is already exclusively attached
    to one node and can't be attached to another
  ```

### 1.2 Root Cause Analysis (RCA)
AWS Elastic Block Store (EBS) is a block device that natively operates in `ReadWriteOnce` (RWO) mode. When the Bank Application scales via HPA or rolling update:
1. Pod 1 is running on `ip-10-0-1-50.ec2.internal` with volume `vol-01234abc` attached.
2. Pod 2 is scheduled on `ip-10-0-2-80.ec2.internal` (in a different AZ or host).
3. The Kubernetes `attachdetach-controller` asks AWS EC2 to attach `vol-01234abc` to `ip-10-0-2-80`.
4. AWS rejects the request because an EBS volume cannot be attached to two instances simultaneously.

### 1.3 Remediation Playbook
* **Short-Term Tactical Fix (Node Affinity/Drain)**:
  Force all replicas to schedule onto the same EC2 node where the volume is already attached:
  ```yaml
  # Patch deployment with pod affinity to co-locate on the same node
  spec:
    template:
      spec:
        affinity:
          podAffinity:
            requiredDuringSchedulingIgnoredDuringExecution:
              - labelSelector:
                  matchExpressions:
                    - key: app.kubernetes.io/name
                      operator: In
                      values: ["bank-app"]
                topologyKey: "kubernetes.io/hostname"
  ```
* **Production Strategic Fix (AWS EFS Migration)**:
  Migrate from AWS EBS to **AWS Elastic File System (EFS)**, which supports `ReadWriteMany` (RWX):
  1. Install AWS EFS CSI Driver.
  2. Create an EFS Filesystem in AWS.
  3. Deploy PVC with `accessModes: [ ReadWriteMany ]` and `storageClassName: efs-sc`.

---

## 2. Incident 2: HPA Reporting `<unknown> / 50%`

### 2.1 Symptoms
Running `kubectl get hpa -n <ns>` shows:
```text
NAME       REFERENCE             TARGETS          MINPODS   MAXPODS   REPLICAS   AGE
bank-app   Deployment/bank-app   <unknown>/50%    2         10        2          12m
```
Pods do not autoscale during load testing.

### 2.2 Root Cause Analysis (RCA)
1. **Missing Resource Requests**: The HPA calculates percentage as $\frac{\text{Actual Usage}}{\text{Requested Usage}}$. If `resources.requests.cpu` is missing in the Pod spec, the denominator is undefined, causing HPA to fail.
2. **Metrics Server Missing or Unhealthy**: The `metrics.k8s.io` API is unavailable because the cluster lacks an active Metrics Server deployment or certificates are invalid.

### 2.3 Remediation Playbook
1. **Verify Metrics Server Health**:
   ```bash
   # Check if Metrics Server pods are running
   kubectl get pods -n kube-system -l k8s-app=metrics-server

   # Test metrics API endpoint
   kubectl top pods -n <ns>
   ```
2. **If Metrics Server is Missing in EKS**:
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```
3. **Verify CPU Requests in Deployment**:
   ```bash
   kubectl get deployment bank-app -n <ns> -o jsonpath="{.spec.template.spec.containers[0].resources.requests}"
   # Must return {"cpu":"200m", ...}
   ```

---

## 3. Incident 3: Pod `CrashLoopBackOff` or Probe Failures

### 3.1 Symptoms
```text
NAME                        READY   STATUS             RESTARTS   AGE
bank-app-797587c699-abcd1   0/1     CrashLoopBackOff   4          6m
```

### 3.2 Root Cause Analysis (RCA)
Check pod logs and termination reasons:
```bash
# Check container logs
kubectl logs <pod-name> -n <ns> --previous

# Check last termination state
kubectl get pod <pod-name> -n <ns> -o jsonpath="{.status.containerStatuses[0].lastState.terminated}"
```

* **Scenario A: Liveness Probe Failure**:
  If events display: `Liveness probe failed: dial tcp 10.0.1.45:80: connect: connection refused`.
  - Cause: Web server died, process crashed, or port misconfigured.
  - Fix: Check Apache error logs inside the container; verify containerPort matches `targetPort: 80`.
* **Scenario B: Permission Denied on Mount Path**:
  If `securityContext.runAsNonRoot: true` (UID 10001) is active, but the EBS volume mount (`/var/www/html/`) is owned by `root:root` (UID 0), Apache fails to write locks/pid files.
  - Fix: Ensure `fsGroup: 10001` is specified in `podSecurityContext`. Kubernetes will recursively chown the volume to group 10001 upon attachment.
* **Scenario C: Read-Only Filesystem Violations**:
  If `readOnlyRootFilesystem: true` is enabled, Apache will fail when trying to write `/var/run/httpd.pid` or `/var/log/httpd/`.
  - Fix: Mount an `emptyDir` volume at `/var/run/` and `/var/log/` for runtime temporary files.

---

## 4. Incident 4: `OOMKilled` (Exit Code 137)

### 4.1 Symptoms
```text
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
```

### 4.2 Root Cause Analysis (RCA)
The Linux kernel OOM (Out Of Memory) Killer terminated the container because its resident memory usage exceeded `resources.limits.memory` (256Mi).

### 4.3 Remediation Playbook
1. Check historical memory consumption:
   ```bash
   kubectl top pod <pod-name> -n <ns>
   ```
2. Increase memory limits in `values.yaml`:
   ```yaml
   resources:
     requests:
       memory: 256Mi
     limits:
       memory: 512Mi
   ```
3. Apply upgrade:
   ```bash
   helm upgrade bank-app . -n <ns> --set resources.limits.memory=512Mi
   ```

---

## 5. Incident 5: Service Has No Endpoints (`<none>`)

### 5.1 Symptoms
Requests to the AWS Load Balancer return `HTTP 502 Bad Gateway` or connection timeouts.
Running `kubectl get endpoints bank-app -n <ns>` returns:
```text
NAME       ENDPOINTS   AGE
bank-app   <none>      8m
```

### 5.2 Root Cause Analysis (RCA)
1. **Selector Mismatch**: The Service `spec.selector` labels do not match the Pod `metadata.labels`.
2. **Readiness Probe Failing**: The pods are running, but their readiness probes are returning non-200, preventing them from being added to the Service's active endpoints.

### 5.3 Remediation Playbook
1. Compare labels:
   ```bash
   # Check service selector
   kubectl get svc bank-app -n <ns> -o jsonpath="{.spec.selector}"

   # Check pod labels
   kubectl get pods -n <ns> --show-labels
   ```
2. Check pod readiness state:
   ```bash
   kubectl describe pod <pod-name> -n <ns> | grep -E "Ready|Readiness"
   ```
   If failing, test endpoint directly from inside the cluster using `kubectl exec` or `curl`.
