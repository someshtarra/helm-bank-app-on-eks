# Bank Application on AWS EKS — Elastic Scaling & Performance Guide

> **Role & Persona**: Performance Architect & DevOps Instructor  
> **Audience**: Platform Engineers, SREs, and Kubernetes Practitioners  
> **Scope**: Horizontal Pod Autoscaling (HPA v2), Metrics Server Mechanics, and Cluster Autoscaling

---

## 1. The Mathematics & Mechanics of HPA v2

The **Horizontal Pod Autoscaler (HPA)** is a Kubernetes control plane controller that continuously compares real-time resource utilization against defined targets.

### 1.1 The Mathematical Autoscaling Formula
The HPA controller executes the following algorithm every `--horizontal-pod-autoscaler-sync-period` (default: 15 seconds):

$$\text{Desired Replicas} = \left\lceil \text{Current Replicas} \times \left( \frac{\text{Current Metric Value}}{\text{Target Metric Value}} \right) \right\rceil$$

#### Real-World Scenario:
* **Current Replicas**: 2 pods
* **Configured Target**: 50% CPU utilization
* **Current Traffic Surge**: Real-time average usage across pods jumps to 85%
* **Calculation**:
  $$\text{Desired Replicas} = \left\lceil 2 \times \left( \frac{85}{50} \right) \right\rceil = \lceil 2 \times 1.7 \rceil = \lceil 3.4 \rceil = 4 \text{ pods}$$
* The HPA controller automatically issues a PATCH request to `Deployment/bank-app` updating `spec.replicas` from 2 to 4.

---

## 2. Why CPU Requests Are Mandatory for HPA

A frequent point of failure in Kubernetes deployments is configuring an HPA without defining `resources.requests.cpu`.

```text
┌─────────────────────────────────────────────────────────────┐
│                   HOW KUBERNETES CALCULATES CPU %           │
│                                                             │
│                      Actual Millicores (from Metrics Server)│
│   CPU %  =  ───────────────────────────────────────────     │
│                     Configured CPU Request Millicores       │
└─────────────────────────────────────────────────────────────┘
```

1. **The Denominator Requirement**:
   Kubernetes does **not** calculate CPU percentage relative to the host node's hardware or the container limit. It calculates utilization relative to the container's **CPU Request**.
2. **Failure Mode**:
   If `resources.requests.cpu` is missing or set to `0`:
   - The denominator is undefined.
   - The HPA status shows: `TARGETS: <unknown>/50%`.
   - The HPA refuses to scale in either direction, leaving the service vulnerable to overload.

---

## 3. Metrics Server & Telemetry Architecture

```text
┌─────────────────────────────────┐
│        Application Pod          │
│   (cgroups CPU/Memory accounting)│
└────────────────┬────────────────┘
                 │
                 ▼ Local scraping
┌─────────────────────────────────┐
│          Kubelet Agent          │
│   (cadvisor: /metrics/resource) │
└────────────────┬────────────────┘
                 │
                 ▼ Periodic poll (every 60s)
┌─────────────────────────────────┐
│     EKS Metrics Server Pod      │
│  (metrics.k8s.io aggregated API)│
└────────────────┬────────────────┘
                 │
                 ▼ Query loop (every 15s)
┌─────────────────────────────────┐
│   K8s HPA Controller Manager    │
└─────────────────────────────────┘
```

1. **cgroups**: The Linux kernel tracks exact CPU cycles used by the container processes.
2. **Kubelet / cAdvisor**: The node kubelet aggregates container resource counters and exposes them locally at `/metrics/resource`.
3. **Metrics Server**: A cluster-wide aggregator that scrapes every node's kubelet, stores metrics in-memory, and registers the `metrics.k8s.io` sub-API.
4. **HPA Controller**: Queries `metrics.k8s.io` to compute the autoscaling equation.

---

## 4. Advanced HPA v2: Dual Metrics & Stabilization Behaviors

The chart leverages `autoscaling/v2` with fine-tuned scaling behaviors:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: bank-app
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
```

### Why Stabilization Windows Matter:
* **The Flapping Problem**: A short spike (e.g., cron job or temporary burst) causes pods to scale up. 30 seconds later, traffic drops; pods terminate. Another spike arrives, and pods scale up again. This constant churning exhausts node resources, degrades caches, and creates latency spikes.
* **The 300-Second Buffer**: `scaleDown.stabilizationWindowSeconds: 300` instructs the controller to look at the maximum calculated replica count over the preceding 5 minutes before initiating a scale-down.
* **Gradual Scale-Down**: The policy limits scale-down to at most 25% of current pods per minute, preventing abrupt capacity collapse.

---

## 5. What Happens When `maxReplicas` is Reached?

When traffic drives CPU above target utilization, but the deployment has scaled to `maxReplicas: 10`:
1. **HPA Saturation**: The HPA cannot create more pods.
2. **Container Limits & Throttling**:
   - If CPU usage reaches `resources.limits.cpu` (500m), CFS (Completely Fair Scheduler) quota throttling engages. Requests experience latency increases.
   - If memory usage reaches `resources.limits.memory` (256Mi), the container is `OOMKilled`.
3. **Upstream Queuing**: The AWS NLB buffers connections until timeout.
4. **DevOps SRE Action**:
   - Set up Prometheus alerts for `kube_horizontalpodautoscaler_status_current_replicas == kube_horizontalpodautoscaler_spec_max_replicas`.
   - Scale cluster worker nodes via Karpenter or Cluster Autoscaler to prepare capacity for higher `maxReplicas`.

---

## 6. Multi-Tier Scaling: Pods vs. Nodes

```text
Traffic Influx
      │
      ▼
┌─────────────────────────────────┐
│     Horizontal Pod Autoscaler   │
│      (Scales Pods: 2 -> 10)     │
└────────────────┬────────────────┘
                 │
                 ▼ Node CPU / Memory Exhausted (Pods stuck in Pending)
┌─────────────────────────────────┐
│    Karpenter / Cluster Auto     │
│     (Provisions new EC2 Nodes)  │
└─────────────────────────────────┘
```

* **HPA**: Adjusts pod counts based on application load.
* **Karpenter / Cluster Autoscaler**: Reacts when unscheduled pods enter `Pending` state due to lack of node CPU/RAM, automatically launching new AWS EC2 instances in <45 seconds.

---

## 7. Load Testing & Autoscaling Verification

Validate HPA behavior in a live staging cluster using **Apache Bench (`ab`)**:

```bash
# 1. Open a terminal to monitor HPA in real time
kubectl get hpa bank-app -n production -w

# 2. In a second terminal, monitor pod creation
kubectl get pods -n production -l app.kubernetes.io/name=bank-app -w

# 3. Generate high HTTP traffic against the LoadBalancer IP
export LB_URL="http://$(kubectl get svc bank-app -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
ab -n 50000 -c 100 $LB_URL/
```
Observe the CPU utilization climb above 50% and watch HPA step replicas up: `2 -> 4 -> 8 -> 10`.
