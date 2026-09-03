# Bank Application on AWS EKS — Technical Presentation Deck

> **Presentation File**: [`presentation/devops-kubernetes-project.pptx`](devops-kubernetes-project.pptx)  
> **Format**: 16:9 Widescreen Executive Slide Deck (21 Slides)  
> **Target Audience**: DevOps Beginners, Kubernetes Learners, Cloud Architects, Interviewers, and Technical Hiring Managers

---

## Slide 1: Title Slide
* **Title**: Bank Application on Kubernetes (AWS EKS)
* **Subtitle**: Enterprise Cloud-Native Workload Architecture
* **Tagline**: Production Readiness Review, Horizontal Elasticity (HPA v2), Zero-Trust RBAC, and Resilient Storage Architecture
* **Author**: Senior DevOps Engineer & Kubernetes Instructor
* **Speaker Notes**:
  > Welcome everyone. Today we are walking through the complete production transformation of the Bank Application on AWS EKS. We will explore architectural flaws in traditional setups, how we fixed them, and the production-grade patterns implemented across autoscaling, storage, security, and lifecycle management.

---

## Slide 2: Business & Technical Problem Statement
* **The Business Challenge**:
  * **High Transaction Volatility**: Rapid surges during paydays and market opens demand instant elasticity.
  * **Strict Zero-Downtime SLA**: In banking, outages cause immediate financial and brand impact.
  * **Regulatory Compliance**: Mandates (PCI-DSS, SOC2) enforce least privilege and isolation.
  * **Cost Governance**: Static over-provisioning inflates AWS compute costs.
* **The Technical Challenge**:
  * **Legacy YAML Sprawl**: Manifests with disjoint namespaces (`default` vs `lab`).
  * **Storage Contention**: Multi-replica pods sharing a single EBS volume (`ReadWriteOnce`) causing `Multi-Attach error`.
  * **Autoscaling Breakdown**: Deprecated HPA v1 without mandatory CPU requests, leaving metrics `<unknown>`.
  * **Security Exposure**: Root containers with dangerous pod deletion privileges.
* **Speaker Notes**:
  > Every architectural design must solve real business problems. Banking systems face intense spikes and strict compliance. If infrastructure is poorly structured, outages occur during scaling and security vulnerabilities emerge.

---

## Slide 3: Technology Stack & Enterprise Tooling
* **AWS EKS**: Managed Kubernetes Control Plane with 99.95% SLA, multi-AZ etcd replication, and VPC CNI integration.
* **Helm v3**: Package management, parameterization via `values.yaml`, and release versioning.
* **Kubernetes HPA v2**: Dynamic horizontal elasticity with dual CPU/Memory metrics and stabilization behavior.
* **AWS EBS CSI Driver**: Dynamic gp3 block storage provisioning with `WaitForFirstConsumer` AZ binding.
* **AWS Network Load Balancer (NLB)**: Ultra-low latency Layer 4 load balancing with cross-zone failover.
* **Apache HTTP Server**: Hardened web server container running as unprivileged UID 10001 with dropped capabilities.
* **Speaker Notes**:
  > Our technology stack combines battle-tested cloud-native components: AWS EKS for control plane reliability, Helm v3 for configuration as code, HPA v2 for elasticity, and modern EBS CSI for persistent storage.

---

## Slide 4: High-Level Architecture & End-to-End Traffic Flow
* **Visual**: Embedded `diagrams/architecture.png`
* **Core Flow Summary**:
  * **Traffic Ingress**: User $\rightarrow$ AWS NLB $\rightarrow$ K8s Service $\rightarrow$ Pods.
  * **Scheduling**: Dedicated frontend nodes via taints & tolerations.
  * **Elasticity**: HPA v2 queries Metrics Server to autoscale pods 2 to 10.
  * **Storage**: Dynamic EBS gp3 volume attached via AWS CSI driver.
  * **RBAC**: Least-privilege ServiceAccount with token automount disabled.
* **Speaker Notes**:
  > Here is the comprehensive architectural diagram. Notice how client requests flow through the AWS Network Load Balancer directly into the Kubernetes Service, which round-robins across healthy pods. Concurrently, HPA monitors workload utilization.

---

## Slide 5: AWS EKS Cluster Topology & Isolation
* **Node Group Architecture**:
  * **Multi-AZ Deployment**: Worker nodes distributed across `us-east-1a` and `us-east-1b` for high availability.
  * **Workload Taints**: Dedicated node groups tainted with `dedicated=frontend:NoSchedule`.
  * **Node Affinity**: Pods declare soft affinity (`preferredDuringScheduling`) to production-labeled instances.
  * **Auto-Healing**: AWS EKS Managed Node Groups automatically replace degraded EC2 instances.
* **Networking & Security Perimeter**:
  * **AWS VPC CNI**: Native VPC IP allocation per pod, eliminating overlay network translation overhead.
  * **Security Groups for Pods**: Direct ENI binding allowing granular firewall rules per microservice.
  * **Private API Server**: EKS control plane accessible via VPN/DirectConnect with public endpoint restricted.
  * **AWS OIDC Identity**: Native federation enabling IAM Roles for Service Accounts (IRSA).
* **Speaker Notes**:
  > In EKS, nodes are separated by Availability Zones. We isolate frontend banking pods on dedicated worker nodes using taints and tolerations to protect them from resource contention.

---

## Slide 6: Helm Chart Structure & Templating Best Practices
* **Standardized Repository Hierarchy**:
  * `Chart.yaml`: Semantic chart metadata (v2 API, appVersion 2.4.58).
  * `values.yaml`: Self-documenting, production-grade default values.
  * `templates/_helpers.tpl`: Reusable template functions for labels and naming.
  * `templates/*.yaml`: Declarative manifests for Deployment, Service, HPA, RBAC, Storage, and PDB.
  * `NOTES.txt`: Post-installation verification commands.
* **Templating Improvements**:
  * **Dynamic Namespaces**: Eliminated hardcoded `default` and `lab`; standardized on `{{ .Release.Namespace }}`.
  * **Standard Labeling**: Applied Kubernetes recommended labels (`app.kubernetes.io/*`) across all objects.
  * **Schema Compliance**: Fixed `roleRef` schema from invalid list to correct map syntax.
  * **Modular Toggles**: Configurable flags for storage, autoscaling, RBAC, and security contexts.
* **Speaker Notes**:
  > We refactored the Helm chart into an enterprise layout with _helpers.tpl for centralized naming and standardized labels. Hardcoded namespaces were completely eliminated.

---

## Slide 7: Deployment Architecture & Pod Lifecycle
* **Deployment Specification**:
  * **Target Image**: `someshtarra/httpd:fox-3D` (Apache HTTP Server).
  * **Resource QoS**: Configured with Burstable QoS class (200m CPU / 128Mi RAM requests).
  * **Non-Root User**: Runs explicitly as UID 10001 with GID 10001.
  * **RollingUpdate**: `maxSurge: 1`, `maxUnavailable: 0` to guarantee zero downtime during releases.
* **Pod Resilience & Placement**:
  * **Tolerations**: Matches `dedicated=frontend:NoSchedule` taints.
  * **PodDisruptionBudget**: Guarantees at least 1 pod is always available during node maintenance.
  * **Volume Mounts**: Conditionally mounts persistent storage at `/var/www/html/`.
  * **Topology Spread**: Distributes pods across distinct nodes and availability zones.
* **Speaker Notes**:
  > The deployment manifest controls the pod lifecycle. We enforce non-root execution, specify precise compute requests, and integrate a PodDisruptionBudget to protect pods during node draining.

---

## Slide 8: Kubernetes Service & AWS Load Balancer
* **Service Layer Configuration**:
  * **Service Type**: `LoadBalancer` (Port 80 $\rightarrow$ TargetPort 80).
  * **Selector Match**: Strictly aligned with deployment pod template labels.
  * **Endpoint Management**: Endpoints automatically updated based on `readinessProbe` status.
  * **Multi-Port Support**: Easily extendable to HTTPS (Port 443) with ACM certificate binding.
* **AWS NLB Controller Annotations**:
  * `aws-load-balancer-type: "external"` — Provisions modern AWS Network Load Balancer.
  * `aws-load-balancer-nlb-target-type: "instance"` — Routes directly to node instance targets.
  * `aws-load-balancer-scheme: "internet-facing"` — Enables public client connectivity.
  * **Performance Advantage**: Layer 4 NLB handles millions of requests/sec with ultra-low latency.
* **Speaker Notes**:
  > By using modern AWS Load Balancer Controller annotations, we provision a high-performance Network Load Balancer rather than the legacy Classic Load Balancer.

---

## Slide 9: Horizontal Pod Autoscaler (HPA v2) Mechanics
* **Visual**: Embedded `diagrams/hpa-flow.png`
* **HPA Scaling Logic**:
  * **Telemetry**: Metrics Server scrapes kubelet `/metrics/resource`.
  * **Sync Period**: Controller evaluates every 15 seconds.
  * **Target**: Scales up when average CPU > 50% or RAM > 80%.
  * **Scale Range**: Dynamically scales between 2 and 10 replicas.
  * **Stabilization**: 300s scale-down delay prevents thrashing.
* **Speaker Notes**:
  > This diagram explains the complete HPA loop. The Metrics Server aggregates CPU usage from kubelets, and the HPA controller calculates target replicas and patches the deployment.

---

## Slide 10: CPU Requests, Limits & Telemetry Mathematics
* **The HPA Formula & CPU Requests**:
  * **Mathematical Formula**: $\text{Desired} = \lceil \text{Current} \times (\text{CurrentUsage} / \text{TargetUsage}) \rceil$.
  * **The Utilization Ratio**: $\text{CPU \%} = (\text{Actual Millicores} / \text{Requested Millicores}) \times 100$.
  * **The Missing Request Pitfall**: If CPU request is missing, denominator is undefined!
  * **Failure State**: HPA displays `<unknown> / 50%` and cannot autoscale.
* **Requests vs. Limits (QoS Mechanics)**:
  * **Requests (200m CPU / 128Mi RAM)**: Guaranteed minimum compute reserved by scheduler.
  * **Limits (500m CPU / 256Mi RAM)**: Hard upper ceiling enforced by Linux kernel cgroups.
  * **CPU Exceeded**: Results in CFS quota CPU throttling (latency rises; process is NOT killed).
  * **Memory Exceeded**: Results in kernel OOM Killer terminating container (Exit Code 137).
* **Speaker Notes**:
  > Understanding the math behind HPA is vital. CPU percentage is calculated against the CPU request. Without requests, HPA fails completely. We also contrast CPU throttling with memory OOMKills.

---

## Slide 11: Storage Architecture: AWS EBS & CSI Driver
* **Visual**: Embedded `diagrams/storage-flow.png`
* **Storage Components**:
  * **StorageClass**: `ebs.csi.aws.com` with `type: gp3`.
  * **Binding Mode**: `WaitForFirstConsumer` ensures volume matches node AZ.
  * **PVC**: Requests 5Gi with `ReadWriteOnce` access mode.
  * **ReclaimPolicy**: `Retain` preserves disk upon PVC deletion.
  * **Mount Path**: `/var/www/html/` for web assets.
* **Speaker Notes**:
  > Persistent storage is managed by the AWS EBS CSI driver. We use gp3 volumes and WaitForFirstConsumer binding to ensure the volume is created in the exact AZ where the pod lands.

---

## Slide 12: Architectural Trade-Off: AWS EBS vs. AWS EFS
* **AWS EBS: ReadWriteOnce (RWO)**:
  * **Storage Type**: Block Device (Virtual SAN hard drive).
  * **Node Attachment**: Strictly limited to 1 EC2 instance at a time.
  * **Failure Mode**: Replicas on Node B fail with `Multi-Attach error`.
  * **Best Use Case**: Single-replica workloads, databases (PostgreSQL, MySQL), or StatefulSets with dedicated volume per pod.
* **AWS EFS: ReadWriteMany (RWX)**:
  * **Storage Type**: Managed Distributed NFSv4.1 File System.
  * **Node Attachment**: Concurrently mountable by 1000+ pods across all AZs.
  * **Horizontal Scaling**: Seamlessly scales alongside HPA replicas (2 to 10).
  * **Best Use Case**: Multi-replica web frontends, shared assets, CMS, and stateless cloud applications.
* **Speaker Notes**:
  > This slide covers the fundamental storage trade-off. EBS cannot scale horizontally across multiple nodes because of the ReadWriteOnce limitation. For multi-replica deployments, AWS EFS (RWX) or S3 object storage is the proper production architecture.

---

## Slide 13: RBAC & ServiceAccount Governance
* **Visual**: Embedded `diagrams/rbac-flow.png`
* **RBAC Highlights**:
  * **Identity**: Dedicated ServiceAccount per application.
  * **Token Security**: `automountServiceAccountToken: false`.
  * **Syntax Fix**: `roleRef` written as map with `apiGroup` singular.
  * **Namespace Fix**: Scoped dynamically to release namespace.
  * **Least Privilege**: Read-only access to ConfigMaps only.
* **Speaker Notes**:
  > RBAC controls who can do what in the cluster. We resolved schema bugs in roleRef and eliminated dangerous pod-deletion permissions, securing the application identity.

---

## Slide 14: Workload Hardening & DevSecOps Standards
* **Container Security Context**:
  * `runAsNonRoot: true` — Enforces execution under unprivileged UID 10001.
  * `allowPrivilegeEscalation: false` — Blocks setuid binary privilege inheritance.
  * `capabilities.drop: ['ALL']` — Strips all standard Linux kernel capabilities.
  * `seccompProfile: RuntimeDefault` — Blocks unauthorized system calls at kernel layer.
* **Enterprise Secrets & Identity**:
  * **AWS IRSA**: Replaces static credentials with temporary IAM OIDC role assumption.
  * **External Secrets Operator**: Syncs database credentials directly from AWS Secrets Manager.
  * **NetworkPolicies**: Restricts ingress/egress traffic to legitimate service paths.
  * **Image Scanning**: Automated vulnerability scanning via Trivy in CI/CD pipeline.
* **Speaker Notes**:
  > Our security posture adheres to CIS Kubernetes benchmarks and the Restricted Pod Security Standard. We run unprivileged containers and eliminate static credentials via IRSA.

---

## Slide 15: Health Probes: Startup, Readiness, & Liveness
* **Startup Probe**:
  * **Purpose**: Verifies process startup.
  * **Config**: HTTP GET on `/` (`failureThreshold: 20`, `period: 5s`). Allows up to 100s for initialization.
  * **Crucial**: Disables liveness probe while active to prevent premature killing.
* **Readiness Probe**:
  * **Purpose**: Controls traffic routing.
  * **Config**: HTTP GET on `/` (`failureThreshold: 3`, `period: 5s`).
  * **Crucial**: Failing probe removes pod IP from Service endpoints without killing container.
* **Liveness Probe**:
  * **Purpose**: Deadlock recovery.
  * **Config**: TCP socket check on port 80 (`period: 10s`).
  * **Crucial**: Avoid deep database checks to prevent cascading cluster restarts.
* **Speaker Notes**:
  > Health probes form a critical triad: Startup protects initialization, Readiness shields users from incomplete responses, and Liveness recovers wedged processes.

---

## Slide 16: Zero-Downtime Rolling Updates
* **RollingUpdate Mechanics**:
  * `maxSurge: 1` — Creates 1 new pod before terminating any existing pod.
  * `maxUnavailable: 0` — Guarantees 100% capacity remains online throughout rollout.
  * **Readiness Gate**: Old pod is only terminated after new pod passes readiness probe.
  * **Traffic Continuity**: Clients experience zero connection drops or 502 errors.
* **PodDisruptionBudget (PDB)**:
  * `minAvailable: 1` — Prevents Kubernetes from terminating all pods during node draining.
  * **Node Upgrades**: Cluster administrator upgrades EKS nodes safely without application downtime.
  * **Voluntary Disruptions**: Protects against accidental manual evictions and autoscaler drains.
* **Speaker Notes**:
  > Zero-downtime updates require maxUnavailable: 0 and readiness probes. The PodDisruptionBudget guarantees that voluntary evictions during cluster upgrades do not cause downtime.

---

## Slide 17: Operational Deployment Workflow
* **Pre-Deployment & Installation**:
  1. **Lint Chart**: `helm lint .` to validate syntax and chart rules.
  2. **Local Render**: `helm template bank-app .` to inspect generated YAML.
  3. **Dry-Run**: `kubectl apply --dry-run=server` to test against EKS API.
  4. **Release Install**: `helm upgrade --install bank-app . --namespace production`.
* **Upgrades & Instant Rollback**:
  * **Track History**: `helm history bank-app -n production` displays all revisions.
  * **Rolling Upgrade**: `helm upgrade bank-app . --set image.tag=v2.0.0`.
  * **Instant Rollback**: `helm rollback bank-app 1 -n production` in <5 seconds.
  * **Status Verification**: `kubectl rollout status deployment/bank-app`.
* **Speaker Notes**:
  > We follow a disciplined deployment lifecycle: linting, dry-run validation, atomic Helm releases, revision history tracking, and single-command rollbacks.

---

## Slide 18: Production Troubleshooting Runbook
* **Multi-Attach Error**:
  * Symptom: Pod stuck in `ContainerCreating`.
  * Cause: Single EBS volume mounted across nodes.
  * Fix: Migrate to AWS EFS or co-locate with pod affinity.
* **HPA `<unknown> / 50%`**:
  * Symptom: HPA target shows `<unknown>`.
  * Cause: Missing CPU requests or Metrics Server dead.
  * Fix: Define `resources.requests.cpu`; restart Metrics Server.
* **OOMKilled (Exit 137)**:
  * Symptom: Container restarts with Exit Code 137.
  * Cause: Container exceeded `resources.limits.memory`.
  * Fix: Increase memory limit or optimize application memory.
* **Empty Endpoints**:
  * Symptom: Service returns 502 Bad Gateway.
  * Cause: Selector mismatch or failed readiness probe.
  * Fix: Align labels; inspect `readinessProbe` endpoint.
* **Speaker Notes**:
  > Our troubleshooting guide provides actionable playbooks for the four most common production incidents: EBS multi-attach conflicts, HPA unknown metrics, OOM kills, and empty service endpoints.

---

## Slide 19: Production Readiness Review Audit
* **Before (Original Flaws)**:
  * ❌ Inconsistent namespaces (`default` vs `lab`) breaking RBAC.
  * ❌ Broken `roleRef` schema syntax failing Kubernetes admission.
  * ❌ Frontend web container granted full pod deletion permissions.
  * ❌ Deprecated `autoscaling/v1` lacking stabilization controls.
  * ❌ EBS RWO volume causing multi-node mount deadlock.
* **After (Production-Grade)**:
  * ✅ Consistent namespace scoping via `{{ .Release.Namespace }}`.
  * ✅ Valid schema-compliant `roleRef` map syntax.
  * ✅ Least-privilege RBAC with token automounting disabled.
  * ✅ Upgraded to `autoscaling/v2` with dual CPU/memory metrics.
  * ✅ Documented EBS limitations and defined AWS EFS blueprint.
  * ✅ Zero-downtime rolling update with `PodDisruptionBudget`.
* **Speaker Notes**:
  > This audit slide demonstrates the value delivered: moving from a fragile, insecure setup to an enterprise-grade, hardened production workload.

---

## Slide 20: Future DevOps & GitOps Platform Roadmap
* **CI/CD & GitOps Automation**:
  * **GitHub Actions**: Automated linting, Trivy vulnerability scanning, and Helm packaging.
  * **Argo CD**: Declarative GitOps deployment with automated drift detection and self-healing.
  * **Terraform**: Infrastructure as Code for provisioning EKS clusters, VPCs, and IAM roles.
  * **Amazon ECR**: Private, signed container registries with immutable digest pinning.
* **Observability & Platform Governance**:
  * **Prometheus & Grafana**: Real-time RED metrics, cluster telemetry, and custom HPA triggers.
  * **Fluent Bit & Loki**: Centralized application log aggregation and search.
  * **Kyverno / OPA Gatekeeper**: Automated policy enforcement for Pod Security Standards.
  * **Karpenter**: Intelligent, high-speed node autoscaling replacing Cluster Autoscaler.
* **Speaker Notes**:
  > Looking ahead, this project serves as the foundation for an end-to-end GitOps platform powered by Argo CD, GitHub Actions, Prometheus, and Karpenter.

---

## Slide 21: DevOps Learning Summary & Key Takeaways
* **Core Technical Competencies**:
  * **Production Kubernetes Architecture**: Deep mastery of Pods, Deployments, Services, and Ingress.
  * **Elastic Autoscaling**: Mathematical mechanics of HPA v2 and Metrics Server integration.
  * **Cloud Storage Realities**: Navigating block vs. network file storage trade-offs in AWS.
  * **Zero-Trust Security**: Enforcing least-privilege RBAC and container security contexts.
* **DevOps Mindset & Value**:
  * **Understanding WHY**: Prioritizing architectural rationale over rote YAML configuration.
  * **Reliability by Default**: Designing for failure with probes, PDBs, and zero-downtime rollouts.
  * **Clear Technical Communication**: Ability to teach and document complex cloud architectures.
  * **Production Readiness**: Bridging the gap between lab exercises and enterprise realities.
* **Speaker Notes**:
  > In conclusion, this project exemplifies the senior DevOps mindset: not just writing YAML, but understanding why configurations work, anticipating production failures, and securing workloads by default.
