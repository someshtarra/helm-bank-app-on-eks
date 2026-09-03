# Bank Application on AWS EKS — DevOps & Kubernetes Interview Guide

> **Author**: Senior DevOps Engineer & Kubernetes Instructor  
> **Purpose**: Technical Interview Preparation based on the Bank Application on AWS EKS Project  
> **Levels Covered**: Junior (Foundations), Mid-Level (Engineering & Operations), Senior/Architect (Design & Trade-Offs)

---

## Table of Contents
1. [Architectural Strategy: Why Kubernetes, EKS, and Helm?](#1-architectural-strategy)
2. [Workload Scaling & Metrics Server (HPA)](#2-workload-scaling--metrics-server)
3. [Cloud Storage & AWS EBS vs. EFS Architecture](#3-cloud-storage--aws-ebs-vs-efs)
4. [Kubernetes RBAC & Zero-Trust Workload Security](#4-kubernetes-rbac--security)
5. [Reliability, Rolling Updates, and Health Probes](#5-reliability-rolling-updates--health-probes)
6. [Production Deployment, Observability, and Operations](#6-production-deployment--operations)

---

## 1. Architectural Strategy

### Q1: Why did you choose Kubernetes for this Bank Application?
**Interview Answer**:  
Kubernetes provides declarative, self-healing infrastructure for enterprise microservices. In a banking context where downtime translates directly into financial and regulatory penalties, Kubernetes delivers:
1. **Zero-downtime rolling updates** with automatic rollbacks if new versions fail health probes.
2. **Elastic horizontal scaling (HPA)** to handle bursty banking transaction volumes.
3. **Infrastructure immutability and portability**, avoiding cloud vendor lock-in.
4. **Fine-grained workload isolation and security policies** meeting financial compliance standards (e.g., PCI-DSS).

### Q2: Why use AWS EKS instead of self-managed Kubernetes on EC2?
**Interview Answer**:  
Running self-managed Kubernetes requires operating, patching, and backing up the `etcd` database and API server control plane across multiple Availability Zones. AWS EKS provides a **managed control plane** with a 99.95% SLA. AWS handles multi-AZ etcd replication, automated control plane scaling, and seamless version upgrades. Furthermore, EKS natively integrates with AWS Identity and Access Management (via IRSA), VPC CNI networking, AWS KMS encryption, and AWS Load Balancers.

### Q3: Why use Helm instead of raw Kubernetes YAML manifests?
**Interview Answer**:  
Raw YAML manifests are static, repetitive, and error-prone across different environments (dev, staging, prod). Helm acts as the package manager for Kubernetes:
1. **Templating and Parameterization**: A single codebase (`templates/`) accepts environment-specific parameters via `values.yaml`.
2. **Release Lifecycle Management**: Helm tracks release revisions in Kubernetes secrets, enabling single-command rollbacks (`helm rollback <release> <rev>`).
3. **Dependency and Version Management**: Charts define explicit semantic versions (`Chart.yaml`) and application versions, integrating smoothly into automated CI/CD pipelines.

---

## 2. Workload Scaling & Metrics Server

### Q4: How does the Horizontal Pod Autoscaler (HPA) work under the hood?
**Interview Answer**:  
The HPA controller runs inside the Kubernetes Controller Manager and executes a control loop every 15 seconds. It queries the `metrics.k8s.io` aggregated API served by the Metrics Server. The HPA calculates desired replicas using the formula:
$$\text{Desired Replicas} = \left\lceil \text{Current Replicas} \times \left( \frac{\text{Current Metric Value}}{\text{Target Metric Value}} \right) \right\rceil$$
When the calculated replica count differs from the deployment's current replica count, the controller issues a PATCH request to update the deployment's `replicas` field.

### Q5: Why are CPU requests strictly required for CPU-based HPA?
**Interview Answer**:  
Because Kubernetes calculates CPU utilization percentage relative to the **CPU Request** of the pod, not the node's physical cores or the container limit:
$$\text{Utilization \%} = \frac{\text{Actual Usage (millicores)}}{\text{Requested CPU (millicores)}} \times 100$$
If `resources.requests.cpu` is omitted, the denominator is undefined. The HPA controller fails to calculate utilization, status displays `<unknown> / 50%`, and no autoscaling will ever occur.

### Q6: Why did you migrate from `autoscaling/v1` to `autoscaling/v2`?
**Interview Answer**:  
`autoscaling/v1` is deprecated and only supports a single target: average CPU percentage. `autoscaling/v2` introduces:
1. **Multi-metric scaling**: Pods can scale concurrently on CPU, memory, and custom Prometheus metrics (e.g., HTTP request rate or queue depth).
2. **Scaling behaviors**: Fine-grained control over stabilization windows (e.g., `stabilizationWindowSeconds: 300` on scale-down) and rate-limiting policies to eliminate flapping/thrashing during temporary traffic pauses.

### Q7: What happens when HPA reaches `maxReplicas` and traffic keeps climbing?
**Interview Answer**:  
When `maxReplicas` is reached:
1. The HPA controller will not scale beyond this ceiling to protect the cluster from budget overruns or resource exhaustion.
2. The existing pods will absorb the traffic until they hit `resources.limits.cpu` (causing CFS CPU throttling and higher latency) or `resources.limits.memory` (causing the kernel to trigger `OOMKilled`).
3. The upstream AWS Load Balancer queues connections, eventually returning HTTP 504 Gateway Timeouts.
4. **Remediation**: Set up proactive alerting at 80% of max replicas, implement Cluster Autoscaler / Karpenter to provision new EC2 nodes, and consider upstream queueing or rate-limiting with an API Gateway.

---

## 3. Cloud Storage & AWS EBS vs. EFS

### Q8: What does `ReadWriteOnce` (RWO) mean in Kubernetes?
**Interview Answer**:  
`ReadWriteOnce` means the volume can be mounted as read-write by **nodes**, not pods. Specifically, it can be mounted by **only one single node** at a time. Multiple pods can read and write to that volume only if all those pods are co-located on the **exact same physical/virtual node**.

### Q9: Why is AWS EBS problematic when paired with a horizontally scaled Deployment?
**Interview Answer**:  
AWS EBS is block storage. An EBS volume cannot be physically attached to two EC2 instances simultaneously (with the exception of specialized Multi-Attach io2 volumes, which require a cluster-aware filesystem like GFS2, not ext4).  
When a Deployment scales across multiple nodes:
1. Pod 1 mounts the EBS volume on Node A.
2. Pod 2 is scheduled on Node B.
3. The cluster attempts to attach the volume to Node B, resulting in:
   `Multi-Attach error for volume ... Volume is already exclusively attached to one node`.
4. Pod 2 remains stuck in `ContainerCreating` indefinitely.

### Q10: How would you resolve this storage limitation in production?
**Interview Answer**:  
Depending on the workload requirements:
1. **Stateless Pattern (Preferred for Web Apps)**: Store state and files externally in AWS S3 or a managed database (Amazon RDS / Aurora). The web pods become fully stateless and require no PVCs.
2. **Shared File Storage (AWS EFS)**: Use AWS Elastic File System with the AWS EFS CSI Driver. EFS supports `ReadWriteMany` (RWX), allowing hundreds of pods across multiple availability zones and nodes to mount the exact same filesystem concurrently.
3. **StatefulSet Pattern**: If running a stateful clustered service (like Elasticsearch or Kafka), use a `StatefulSet` with `volumeClaimTemplates` so every replica receives its own dedicated, isolated EBS volume.

### Q11: What is the EBS CSI Driver, and why is `WaitForFirstConsumer` used?
**Interview Answer**:  
The **Container Storage Interface (CSI)** driver is an out-of-tree plugin that allows Kubernetes to manage the lifecycle of AWS EBS volumes (provisioning, attaching, mounting, snapshotting).  
`volumeBindingMode: WaitForFirstConsumer` delays the creation and binding of the EBS volume until the pod is actually scheduled onto a node. Because EBS volumes are tied to a specific Availability Zone (e.g., `us-east-1a`), creating the volume immediately could place it in AZ-a while the pod is scheduled on a node in AZ-b, causing a permanent scheduling deadlock. `WaitForFirstConsumer` guarantees the volume is provisioned in the exact AZ of the selected node.

---

## 4. Kubernetes RBAC & Security

### Q12: Explain the difference between a Role and a RoleBinding.
**Interview Answer**:  
* **Role**: Defines a set of permissions (API groups, resources, and allowed verbs like `get`, `list`, `create`) within a specific namespace. It defines *what* actions can be taken.
* **RoleBinding**: Connects the Role to one or more **Subjects** (such as a `ServiceAccount`, User, or Group). It defines *who* gets to perform those actions within that namespace.
*(For cluster-wide scope, `ClusterRole` and `ClusterRoleBinding` are used).*

### Q13: What was the security vulnerability in the original RBAC configuration?
**Interview Answer**:  
The legacy chart granted:
```yaml
resources: ["pods"]
verbs: ["delete", "list", "get", "create", "patch", "watch"]
```
This violates the **Principle of Least Privilege**. If an attacker compromised the public-facing Apache web server, they could use the mounted ServiceAccount token to delete cluster pods, disrupt banking services, or create a malicious pod with host filesystem mounts to escape into the underlying EC2 node.

### Q14: How did you harden the ServiceAccount and container security?
**Interview Answer**:  
1. **Token Automounting**: Set `automountServiceAccountToken: false` on the ServiceAccount and Pod spec because the frontend web app does not need to query the Kubernetes API.
2. **Non-Root Execution**: Configured `securityContext.runAsNonRoot: true`, running as UID `10001`.
3. **Privilege Escalation**: Set `allowPrivilegeEscalation: false` to block setuid binaries.
4. **Capability Dropping**: Configured `capabilities.drop: ["ALL"]` to strip unnecessary Linux kernel capabilities.
5. **Seccomp Profile**: Enforced `seccompProfile.type: RuntimeDefault` to restrict system calls.

---

## 5. Reliability, Rolling Updates, and Health Probes

### Q15: What is the difference between Startup, Readiness, and Liveness probes?
**Interview Answer**:  
* **Startup Probe**: Determines if the application process has initialized. While the startup probe is executing, readiness and liveness probes are disabled. It protects slow-starting applications from being prematurely terminated.
* **Readiness Probe**: Determines if the pod is ready to accept client traffic. If it fails, the pod's IP is removed from the Service's endpoint slices. The container is **not** killed.
* **Liveness Probe**: Determines if the container process is alive. If it fails `failureThreshold` times, the kubelet **kills and restarts** the container.

### Q16: Why should you avoid querying databases in a liveness probe?
**Interview Answer**:  
If a downstream database slows down or suffers a transient outage, every application pod's liveness probe will fail simultaneously. The kubelet will restart all pods at once in a cascading crash loop. Instead, database health should be checked by a readiness probe (to temporarily pull the pod from traffic routing) or handled via circuit breakers.

### Q17: How does this chart achieve zero-downtime rolling updates?
**Interview Answer**:  
Through three coordinated settings:
1. **`maxUnavailable: 0`**: Ensures no existing pod is terminated before a replacement pod is online.
2. **`maxSurge: 1`**: Temporarily provisions a new pod replica during deployment.
3. **`readinessProbe` Integration**: The old pod is only terminated after the new pod passes its readiness probe and the Service has registered its new endpoint.
4. **`PodDisruptionBudget`**: Protects against simultaneous eviction during cluster maintenance and node draining.

---

## 6. Production Deployment, Observability, and Operations

### Q18: What is the purpose of the AWS Load Balancer Controller annotations on the Service?
**Interview Answer**:  
By default, a `type: LoadBalancer` Service in AWS creates a legacy Classic Load Balancer (CLB). By specifying:
```yaml
service.beta.kubernetes.io/aws-load-balancer-type: "external"
service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "instance"
```
The AWS Load Balancer Controller provisions a modern **Network Load Balancer (NLB)**. NLBs offer ultra-low latency, support TLS termination, handle millions of RPS, and route directly to node instance targets.

### Q19: How would you debug an application pod stuck in `CrashLoopBackOff`?
**Interview Answer**:  
I follow a structured triage workflow:
1. Run `kubectl describe pod <pod-name>` to inspect recent lifecycle events (probe failures, mount errors).
2. Check logs: `kubectl logs <pod-name> --previous` to see why the prior container process exited.
3. Inspect termination state: Check `exitCode` (e.g., `Exit Code 137` indicates `OOMKilled`; `Exit Code 1` indicates application crash).
4. If permissions are suspected, verify volume ownership against `fsGroup` and `runAsUser`.

### Q20: How would you monitor this banking workload in production?
**Interview Answer**:  
Implement full-stack observability:
1. **Metrics**: Deploy Prometheus Operator to scrape cAdvisor, kube-state-metrics, and the Apache Prometheus exporter (`/metrics`). Visualize real-time latency, request rates, error codes (RED metrics), and CPU/memory in Grafana dashboards.
2. **Logs**: Aggregate application stdout and access logs using Fluent Bit or Promtail into Grafana Loki or Amazon CloudWatch.
3. **Tracing**: Implement OpenTelemetry or AWS X-Ray to trace user requests through the load balancer, ingress, web tier, and backend APIs.
4. **Alerting**: Configure Prometheus Alertmanager for critical alerts: high 5xx error rate, pod restarts, HPA saturation, and PVC disk utilization > 80%.
