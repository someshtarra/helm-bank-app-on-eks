# Bank Application on AWS EKS — System Architecture & Design Guide

> **Role & Persona**: Senior Cloud Architect & DevOps Instructor  
> **Audience**: Cloud Engineers, SREs, Kubernetes Students, and Technical Hiring Managers  
> **Repository**: [helm-bank-app-on-eks](https://github.com/someshtarra/helm-bank-app-on-eks)

---

## 1. Executive Summary & Architectural Overview

The **Bank Application** is a production-grade, highly available web service deployed on **Amazon Elastic Kubernetes Service (AWS EKS)** using **Helm v3**. The architecture balances resilience, automated horizontal elasticity, strict zero-trust security, and cloud storage considerations.

### High-Level Architectural Flow

```text
                                 [ End Users / Public Internet ]
                                                │
                                                ▼ (HTTPS / HTTP:80)
                               ┌─────────────────────────────────┐
                               │    AWS Network Load Balancer    │
                               │   (NLB - Cross-Zone Enabled)    │
                               └─────────────────────────────────┘
                                                │
                                                ▼ (NodePort / Instance Target)
                               ┌─────────────────────────────────┐
                               │       Kubernetes Service        │
                               │      (Type: LoadBalancer)       │
                               └─────────────────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        │ (Round-Robin Endpoint Routing via kube-proxy) │
                        ▼                                               ▼
             ┌─────────────────────┐                         ┌─────────────────────┐
             │  Application Pod 1  │                         │  Application Pod 2  │
             │ (Apache HTTP Server)│                         │ (Apache HTTP Server)│
             └──────────┬──────────┘                         └──────────┬──────────┘
                        │                                               │
                        │    ▲                                          │    ▲
    [Startup/Readiness/ │    │ [HPA CPU/Mem Metric] [Startup/Readiness/ │    │ [HPA CPU/Mem Metric]
        Liveness Probes]│    │ (Scraped by Kubelet)     Liveness Probes]│    │ (Scraped by Kubelet)
                        │    │                                          │    │
                        ▼    │                                          ▼    │
             ┌─────────────────────┐                         ┌─────────────────────┐
             │ AWS EBS CSI Driver  │                         │ AWS EBS CSI Driver  │
             └──────────┬──────────┘                         └──────────┬──────────┘
                        │                                               │
                        ▼                                               ▼
             ┌─────────────────────────────────────────────────────────────────────┐
             │       PersistentVolumeClaim (PVC: 5Gi gp3 ext4 - ReadWriteOnce)     │
             │       *Architectural Limitation: Bound exclusively to Node 1*       │
             └─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Architectural Subsystems

### 2.1 Ingress & Traffic Management Subsystem

1. **AWS Network Load Balancer (NLB)**:
   - Configured via Kubernetes annotations on the Service:
     - `service.beta.kubernetes.io/aws-load-balancer-type: "external"`
     - `service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "instance"`
     - `service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"`
   - Provides ultra-low latency Layer 4 load balancing capable of handling millions of requests per second with automatic multi-AZ failover.
2. **Kubernetes Service**:
   - Acts as an internal Layer 4 proxy and stable virtual IP (ClusterIP abstraction).
   - Dynamically tracks ready pods using endpoint slices governed by `readinessProbe`.
   - Selector labels match exactly:
     ```yaml
     app.kubernetes.io/name: bank-app
     app.kubernetes.io/instance: {{ .Release.Name }}
     ```

### 2.2 Elastic Autoscaling Subsystem (HPA v2)

```text
┌─────────────────┐       Scrapes /metrics/resource       ┌──────────────────┐
│  Kubelet Agent  │ ────────────────────────────────────► │  Metrics Server  │
└─────────────────┘                                       └────────┬─────────┘
                                                                   │
                                                                   │ Exposes custom/resource
                                                                   │ metrics via metrics.k8s.io
                                                                   ▼
┌─────────────────┐       Scales Replicas (1 to 10)       ┌──────────────────┐
│   Deployment    │ ◄──────────────────────────────────── │  HPA Controller  │
└────────┬────────┘                                       └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Running Pods   │
└─────────────────┘
```

- **Autoscaling Mechanism**:
  - Implements **`autoscaling/v2`** with dual metrics: **CPU utilization (50%)** and **Memory utilization (80%)**.
  - **Stabilization Windows**:
    - `scaleDown.stabilizationWindowSeconds: 300`: Dampens scale-down events to prevent thrashing/flapping during intermittent traffic pauses.
    - `scaleUp.stabilizationWindowSeconds: 0`: Immediate scale-up to absorb incoming surges.
  - **Mathematical Requirement**:
    - The HPA formula calculates:
      $$\text{Desired Replicas} = \left\lceil \text{Current Replicas} \times \left( \frac{\text{Current Metric Value}}{\text{Target Metric Value}} \right) \right\rceil$$
    - Because CPU percentage is computed against `resources.requests.cpu`, omitting CPU requests completely disables autoscaling and causes HPA to report `<unknown> / 50%`.

---

## 3. Storage Architecture & The AWS EBS `ReadWriteOnce` Dilemma

### 3.1 The Mechanical Reality of AWS EBS

AWS Elastic Block Store (EBS) is virtual block storage (SAN-style virtual hard drives) physically networked to specific EC2 compute instances.

```text
[ AWS AZ: us-east-1a ]                          [ AWS AZ: us-east-1b ]
┌───────────────────────────┐                   ┌───────────────────────────┐
│      EC2 Node Alpha       │                   │       EC2 Node Beta       │
│  ┌─────────────────────┐  │                   │  ┌─────────────────────┐  │
│  │     Pod 1 (RWO)     │  │                   │  │     Pod 2 (RWO)     │  │
│  └──────────┬──────────┘  │                   │  └──────────┬──────────┘  │
└─────────────┼─────────────┘                   └─────────────┼─────────────┘
              │                                               │
              ▼ (Attaches via AWS NVMe)                       ▼ (FAILED ATTACHMENT!)
┌───────────────────────────┐                   ┌───────────────────────────┐
│     AWS EBS gp3 Volume    │                   │   Multi-Attach Error:     │
│   (ReadWriteOnce / ext4)  │                   │   Already attached to     │
│  Locked to Node Alpha     │                   │   Node Alpha!             │
└───────────────────────────┘                   └───────────────────────────┘
```

### 3.2 The Flaw in the Original Configuration

In the original configuration:
1. `replicas: 2` (and HPA up to 10) was defined.
2. All replicas were configured to mount the same PVC: `ebs-pvc`.
3. The PVC requested `accessModes: [ ReadWriteOnce ]` backed by `ebs.csi.aws.com`.

**What Happens in Production**:
1. When Pod 1 is scheduled on `Node Alpha`, the AWS EBS CSI driver calls `ec2:AttachVolume` and mounts the gp3 volume on `Node Alpha`.
2. When the Kubernetes scheduler places Pod 2 on `Node Beta` (for high availability or node capacity reasons), Kubernetes attempts to attach the same EBS volume to `Node Beta`.
3. AWS EC2 rejects the call:
   ```text
   Warning  FailedAttachVolume  3m   attachdetach-controller
   Multi-Attach error for volume "pvc-87a23...": Volume is already exclusively attached
   to one node and can't be attached to another
   ```
4. Pod 2 remains stuck indefinitely in `ContainerCreating` or `FailedMount`.
5. Under traffic surges, HPA attempts to scale from 2 to 10 pods. Every new pod scheduled on any node other than `Node Alpha` fails, starving the application of compute capacity!

### 3.3 Storage Options & Trade-Off Matrix

| Strategy | Storage Type | Access Mode | Multi-Node Scalability | Cost & Complexity | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Option 1: AWS EFS (Recommended for Shared Data)** | Managed NFSv4 Network File System | `ReadWriteMany` (RWX) | **Unlimited**: Thousands of pods across all AZs can mount simultaneously. | Moderate; requires AWS EFS CSI driver and EFS mount targets. | Shared static assets, CMS (WordPress, Drupal), report uploads, shared caches. |
| **Option 2: Stateless + S3 Object Storage** | AWS S3 REST API / SDK | N/A (Object) | **Unlimited**: Global scale, zero node attachment constraints. | Lowest cost, highest durability (99.999999999%). | 12-Factor cloud-native web apps; storing logs, user avatars, transaction PDFs. |
| **Option 3: StatefulSet with VolumeClaimTemplates** | AWS EBS gp3 | `ReadWriteOnce` (RWO) | **Isolated**: Each pod replica gets its *own unique* dedicated EBS volume. | Predictable; disk per replica. | Databases (PostgreSQL, MySQL), distributed brokers (Kafka, RabbitMQ, Redis). |
| **Option 4: Single Pod EBS / Node Affinity Lock** | AWS EBS gp3 | `ReadWriteOnce` (RWO) | **Constrained**: All pods forced to the exact same EC2 node via pod affinity. | Low cost; high blast-radius risk (node failure kills all replicas). | Dev/lab testing or legacy monolithic applications. |

---

## 4. RBAC & Zero-Trust Security Subsystem

### 4.1 RBAC Architecture

Kubernetes Role-Based Access Control (RBAC) enforces granular permissions against the Kubernetes API Server (`kube-apiserver`).

```text
┌─────────────────────┐
│  Bank App Container │
└──────────┬──────────┘
           │ (Runs as UID 10001 - non-root)
           ▼
┌─────────────────────────────────┐
│     Dedicated ServiceAccount    │
│  (automountServiceAccountToken: │
│              false)             │
└────────────────┬────────────────┘
                 │
                 ▼ Bound via RoleBinding in release namespace
┌─────────────────────────────────┐
│           RoleBinding           │
│   (apiGroup: rbac.auth.k8s.io)  │
└────────────────┬────────────────┘
                 │
                 ▼ Refers to Role
┌─────────────────────────────────┐
│              Role               │
│  rules:                         │
│  - apiGroups: [""]              │
│    resources: ["configmaps"]    │
│    verbs: ["get", "list"]       │
└─────────────────────────────────┘
```

### 4.2 Principle of Least Privilege Analysis

- **The Original Vulnerability**:
  - The legacy `role.yaml` granted:
    ```yaml
    verbs: ["delete", "list", "get", "create", "patch", "watch"]
    resources: ["pods"]
    ```
  - **Attack Scenario**: If an attacker exploited an HTTP vulnerability in the web server, they could extract the projected service account token from `/var/run/secrets/kubernetes.io/serviceaccount/token`, authenticate to `kube-apiserver`, and execute `kubectl delete pods --all` or deploy crypto-mining pods inside the cluster.
- **The Production Fix**:
  1. Set `automountServiceAccountToken: false` on both ServiceAccount and Deployment spec. The web pod receives **no API token** at all.
  2. If the application requires runtime configuration discovery, grant only read-only (`get`, `list`) access to specific ConfigMaps.

---

## 5. Pod Lifecycle & Health Probe Mechanics

```text
Container Starts
       │
       ▼
┌─────────────────────────┐
│      startupProbe       │ ◄─── Checks if container initialization is complete.
│    (HTTP / - port 80)   │      Disables readiness & liveness probes until it succeeds.
└──────────┬──────────────┘
           │ SUCCESS
           ▼
┌─────────────────────────────────────────────────────────┐
│                Parallel Operational Loops               │
│                                                         │
│   ┌─────────────────────────┐ ┌─────────────────────┐   │
│   │     readinessProbe      │ │    livenessProbe    │   │
│   │   (HTTP / - port 80)    │ │ (TCP Socket port 80)│   │
│   └──────────┬──────────────┘ └──────────┬──────────┘   │
│              │                           │              │
│       FAILURE│ SUCCESS            FAILURE│ SUCCESS      │
│              ▼                           ▼              │
│     ┌─────────────────┐         ┌─────────────────┐     │
│     │ Remove from     │         │ Restart         │     │
│     │ Service Endpts  │         │ Container       │     │
│     │ (Zero Traffic)  │         │ (kubelet kill)  │     │
│     └─────────────────┘         └─────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

1. **`startupProbe`**:
   - `failureThreshold: 20`, `periodSeconds: 5` = Up to **100 seconds** startup allowance.
   - Prevents slow-starting containers from being prematurely killed by the liveness probe.
2. **`readinessProbe`**:
   - Checks `httpGet` on `/`. If the app is overloaded or updating local cache, it returns non-200.
   - Action: Pod IP is removed from the Service endpoints without restarting the process.
3. **`livenessProbe`**:
   - Checks `tcpSocket` on port 80.
   - Action: If the web process completely deadlocks or drops the socket, kubelet restarts the container.
   - **Architectural Best Practice**: Never make a liveness probe query downstream databases; if the database slows down, all frontend pods will restart simultaneously, transforming a minor database hiccup into a catastrophic full-cluster outage.

---

## 6. Scheduling, Affinity, and Toleration Architecture

To prevent frontend bank workloads from competing with heavy backend batch processing or machine learning tasks, dedicated worker nodes are designated in the EKS cluster:

1. **Tolerations**:
   ```yaml
   tolerations:
     - key: dedicated
       operator: Equal
       value: frontend
       effect: NoSchedule
   ```
   Allows the Bank Application pods to schedule onto nodes tainted with `dedicated=frontend:NoSchedule`.
2. **Node Affinity**:
   ```yaml
   nodeAffinity:
     preferredDuringSchedulingIgnoredDuringExecution:
       - weight: 80
         preference:
           matchExpressions:
             - key: environment
               operator: In
               values: ["production"]
   ```
   Soft-schedules pods to production-labeled worker nodes while allowing fallback scheduling if production nodes are saturated.
