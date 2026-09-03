# Bank Application on AWS EKS — Security & Governance Architecture

> **Role & Persona**: Cloud Security Architect & DevSecOps Lead  
> **Audience**: Security Engineers, Compliance Officers, and Platform Architects  
> **Standards Alignment**: CIS Kubernetes Benchmark v1.8, NIST SP 800-190, AWS Well-Architected Security Pillar

---

## 1. Zero-Trust Security Architecture Overview

In an enterprise banking environment, security cannot rely purely on perimeter defenses. The Bank Application adopts a **Defense-in-Depth (DiD)** strategy across four distinct boundaries:

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Perimeter Boundary: AWS WAF, Security Groups, NLB        │
├─────────────────────────────────────────────────────────────┤
│ 2. Network Boundary: Calico / AWS VPC CNI NetworkPolicies   │
├─────────────────────────────────────────────────────────────┤
│ 3. Cluster Boundary: Least-Privilege RBAC & Namespace Scopes│
├─────────────────────────────────────────────────────────────┤
│ 4. Workload Boundary: Non-Root Containers & PSS Restricted  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Workload & Container Hardening

### 2.1 Pod Security Standards (PSS) Compliance
The chart is designed to comply with the **Restricted** profile of Kubernetes Pod Security Standards:

| Security Parameter | Production Setting | Security Objective / Threat Prevented |
| :--- | :--- | :--- |
| `runAsNonRoot` | `true` | Prevents containers from executing with root privileges (`UID 0`). Mitigates host takeover via container escape vulnerabilities. |
| `runAsUser` / `runAsGroup` | `10001` | Runs as an explicit unprivileged UID/GID. |
| `fsGroup` | `10001` | Grants the unprivileged group ownership of mounted volumes without requiring `chown` as root. |
| `allowPrivilegeEscalation` | `false` | Disables the `setuid` binary bit, preventing processes from gaining more privileges than their parent process. |
| `capabilities.drop` | `["ALL"]` | Strips all default Linux kernel capabilities (such as `CAP_NET_RAW`, `CAP_SYS_ADMIN`), restricting the process to standard user execution. |
| `seccompProfile.type` | `RuntimeDefault` | Enforces the container runtime's default secure system call filter, blocking dangerous kernel syscalls. |

### 2.2 Pod Security Context Manifest
```yaml
podSecurityContext:
  fsGroup: 10001
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false  # Note: Mount tmpfs on /var/run and /var/log for true readOnly
  capabilities:
    drop:
      - ALL
```

---

## 3. RBAC & Least-Privilege Governance

### 3.1 Security Flaw in Original Legacy Configuration
The original legacy manifest `role.yaml` contained an egregious security violation:
```yaml
# VULNERABLE LEGACY CONFIGURATION (DO NOT USE)
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["delete", "list", "get", "create", "patch", "watch"]
```

#### Why This is a Critical Production Vulnerability:
1. **Lateral Movement & Cluster Takeover**: If an attacker discovers a Remote Code Execution (RCE) flaw in the Apache web application, they inherit the pod's identity.
2. **Cluster Sabotage**: Armed with `verbs: ["delete"]` on `resources: ["pods"]`, the compromised pod can issue an API call to delete every other pod in the namespace, including databases and authentication microservices.
3. **Privilege Escalation**: With `verbs: ["create"]` on `pods`, the attacker can deploy a privileged pod that mounts the host node's root filesystem (`/host`) and gains complete control over the underlying EC2 instance!

### 3.2 The Hardened Production RBAC Implementation
1. **Disable Unnecessary Token Automounting**:
   Most web applications never need to communicate with the Kubernetes API Server. By default, Kubernetes mounts a JWT token at `/var/run/secrets/kubernetes.io/serviceaccount/token`.
   The hardened chart disables this token projection:
   ```yaml
   # serviceaccount.yaml & deployment.yaml
   automountServiceAccountToken: false
   ```
2. **Scoped, Read-Only Permissions**:
   If the application requires runtime discovery, restrict verbs strictly to read-only operations on non-sensitive assets:
   ```yaml
   # role.yaml
   rules:
     - apiGroups: [""]
       resources: ["configmaps"]
       verbs: ["get", "list", "watch"]
   ```

---

## 4. Cloud Identity & Secret Management

### 4.1 AWS IAM Roles for Service Accounts (IRSA)
In AWS EKS, applications should **never** store static AWS Access Keys (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) in Kubernetes Secrets or environment variables.

Instead, use **IRSA**:
1. An IAM Role is created with a trust policy tied to the EKS OIDC provider.
2. The ServiceAccount is annotated with the IAM Role ARN:
   ```yaml
   serviceAccount:
     annotations:
       eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/BankAppEKSRole
   ```
3. AWS EKS automatically injects a short-lived, auto-rotating Web Identity Token that the AWS SDK uses to assume the IAM role securely.

### 4.2 Enterprise Secret Management Architecture
For sensitive banking credentials (database passwords, encryption keys, API tokens):

```text
┌───────────────────────────┐
│ AWS Secrets Manager / KMS │
└─────────────┬─────────────┘
              │ Synchronized securely via IRSA
              ▼
┌───────────────────────────┐
│ External Secrets Operator │
│  (ESO) / AWS CSI Driver   │
└─────────────┬─────────────┘
              │ Materialized as native K8s Secret (In-Memory tmpfs)
              ▼
┌───────────────────────────┐
│     Bank Application      │
└───────────────────────────┘
```

---

## 5. Network Isolation with NetworkPolicies

To prevent lateral traversal within the cluster, apply Kubernetes `NetworkPolicy` to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: bank-app-network-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: bank-app
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 80
  egress:
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53  # CoreDNS resolution
```

---

## 6. CIS Kubernetes Benchmark Compliance Checklist

* [x] **5.1.1**: Ensure that the cluster-admin role is only used where necessary.
* [x] **5.1.3**: Minimize wildcard use in Roles and ClusterRoles.
* [x] **5.1.5**: Ensure that default service accounts are not actively used.
* [x] **5.1.6**: Ensure that Service Account Tokens are only mounted where necessary (`automountServiceAccountToken: false`).
* [x] **5.2.1**: Minimize the admission of privileged containers.
* [x] **5.2.2**: Ensure containers do not run with root privileges (`runAsNonRoot: true`).
* [x] **5.2.4**: Ensure containers have dropped default capabilities (`capabilities.drop: ["ALL"]`).
* [x] **5.2.5**: Ensure privilege escalation is disallowed (`allowPrivilegeEscalation: false`).
