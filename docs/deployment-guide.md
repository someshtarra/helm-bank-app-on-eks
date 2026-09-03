# Bank Application on AWS EKS — Production Deployment Guide

> **Role & Persona**: Senior DevOps Engineer & Technical Writer  
> **Audience**: Platform Engineers, SREs, and DevOps Practitioners  
> **Scope**: AWS EKS Cluster Prerequisites, Helm Deployment, Upgrades, Rollbacks, and Teardown

---

## 1. Prerequisites & Cluster Requirements

Before deploying the Helm chart, ensure your local workstation and target AWS account have the following configured:

### 1.1 Tooling & Versions
* **AWS CLI**: `>= 2.15.0` (configured with appropriate IAM credentials via `aws configure`)
* **kubectl**: `>= v1.28.0`
* **Helm**: `>= v3.12.0`
* **eksctl**: `>= 0.170.0` (optional, for cluster bootstrap)

```bash
# Verify tooling versions
aws --version
kubectl version --client
helm version
```

### 1.2 AWS EKS Cluster & OIDC Setup
The target EKS cluster must have an IAM OIDC provider enabled to support IAM Roles for Service Accounts (IRSA).

```bash
# Set environment variables
export CLUSTER_NAME="bank-eks-cluster"
export AWS_REGION="us-east-1"
export NAMESPACE="production"

# Verify or associate IAM OIDC Provider
eksctl utils associate-iam-oidc-provider \
  --cluster $CLUSTER_NAME \
  --region $AWS_REGION \
  --approve
```

### 1.3 AWS EBS CSI Driver Add-On Installation
Because this chart uses dynamic EBS gp3 provisioning via `ebs.csi.aws.com`, the **AWS EBS CSI Driver** must be installed on your EKS cluster with the required IAM policy.

```bash
# 1. Create IAM Role with AmazonEBSCSIDriverPolicy
eksctl create iamserviceaccount \
  --name ebs-csi-controller-sa \
  --namespace kube-system \
  --cluster $CLUSTER_NAME \
  --region $AWS_REGION \
  --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
  --approve \
  --role-only \
  --role-name AmazonEKS_EBS_CSI_DriverRole

# 2. Install the AWS EBS CSI EKS Addon
eksctl create addon \
  --name aws-ebs-csi-driver \
  --cluster $CLUSTER_NAME \
  --region $AWS_REGION \
  --service-account-role-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/AmazonEKS_EBS_CSI_DriverRole \
  --force
```

### 1.4 Dedicated Node Group Taints & Labels
The chart is configured to schedule pods on nodes tainted with `dedicated=frontend:NoSchedule` and labeled `environment=production`. If you are using dedicated nodes, ensure your node group has these applied:

```bash
# Check existing node labels and taints
kubectl get nodes --show-labels

# Example taint and label a node (if managing manually)
kubectl taint nodes <node-name> dedicated=frontend:NoSchedule --overwrite
kubectl label nodes <node-name> environment=production --overwrite
```

*(Note: If testing in a generic test cluster without taints, set `tolerations: []` and `affinity: {}` in your `values.yaml` or via `--set`).*

---

## 2. Pre-Deployment Validation & Linting

Always validate the Helm chart locally prior to applying changes to the cluster.

```bash
# 1. Lint the Helm chart for syntax and best practices
helm lint .

# 2. Render templates locally to inspect generated Kubernetes YAML
helm template bank-app . \
  --namespace $NAMESPACE \
  --set replicaCount=2 \
  > /tmp/rendered-bank-app.yaml

# 3. Perform a Kubernetes dry-run validation against the API server
kubectl apply --dry-run=server -f /tmp/rendered-bank-app.yaml -n $NAMESPACE
```

---

## 3. Step-by-Step Installation

### Step 3.1: Create the Dedicated Namespace
```bash
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
```

### Step 3.2: Install the Helm Release
Deploy the chart using `helm install` or `helm upgrade --install`:

```bash
helm upgrade --install bank-app . \
  --namespace $NAMESPACE \
  --create-namespace \
  --values values.yaml \
  --wait \
  --timeout 10m
```

### Step 3.3: Verify Deployment Resources
```bash
# 1. Check all resources in the namespace
kubectl get all,pvc,hpa,pdb,sa -n $NAMESPACE

# 2. Confirm storage class and persistent volume claim binding
kubectl get sc
kubectl get pvc -n $NAMESPACE

# 3. Check HPA status and metric collection
kubectl get hpa bank-app -n $NAMESPACE

# 4. Describe service to retrieve the AWS Network Load Balancer hostname
kubectl describe svc bank-app -n $NAMESPACE
```

---

## 4. Customizing Deployments Across Environments

Use environment-specific values files rather than modifying the base `values.yaml`.

### Example: Staging Deployment (`values-staging.yaml`)
```yaml
replicaCount: 1
autoscaling:
  enabled: false
resources:
  requests:
    cpu: 100m
    memory: 64Mi
  limits:
    cpu: 250m
    memory: 128Mi
storage:
  enabled: false
tolerations: []
affinity: {}
```

Deploy to staging:
```bash
helm upgrade --install bank-app . \
  --namespace staging \
  --create-namespace \
  -f values-staging.yaml
```

---

## 5. Zero-Downtime Upgrades & Rollbacks

### 5.1 Zero-Downtime Rolling Upgrade Mechanics
The chart is configured with a deterministic zero-downtime rolling update strategy:
```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```
- **`maxUnavailable: 0`**: Ensures Kubernetes does not terminate an old pod until the new pod is confirmed completely healthy by both the `startupProbe` and `readinessProbe`.
- **`maxSurge: 1`**: Temporarily provisions 1 extra pod during the transition.
- **`PodDisruptionBudget`**: Guarantees at least 1 pod remains active during involuntary disruptions (node drains, cluster upgrades).

To trigger a rolling update with a new container image:
```bash
helm upgrade bank-app . \
  --namespace $NAMESPACE \
  --set image.tag="v2.0.0" \
  --wait

# Monitor rollout progression in real time
kubectl rollout status deployment/bank-app -n $NAMESPACE
```

### 5.2 Revision History & Instant Rollback
Helm maintains an immutable ledger of every release revision in Kubernetes secrets.

```bash
# View release revision history
helm history bank-app -n $NAMESPACE

# Output example:
# REVISION  UPDATED                   STATUS      CHART           APP VERSION  DESCRIPTION
# 1         Thu Sep  3 10:00:00 2026  superseded  bank-app-1.0.0  2.4.58       Install complete
# 2         Thu Sep  3 10:15:00 2026  deployed    bank-app-1.0.0  2.4.58       Upgrade to v2.0.0

# Instantly rollback to Revision 1 in the event of an issue
helm rollback bank-app 1 -n $NAMESPACE

# Confirm rollback status
kubectl rollout status deployment/bank-app -n $NAMESPACE
```

---

## 6. Teardown & Resource Cleanup

To remove the application and prevent orphaned cloud resources:

```bash
# 1. Uninstall the Helm release
helm uninstall bank-app -n $NAMESPACE

# 2. Check if the PersistentVolumeClaim was deleted
kubectl get pvc -n $NAMESPACE

# IMPORTANT AWS NOTE on ReclaimPolicy: Retain:
# Because StorageClass is configured with 'reclaimPolicy: Retain',
# deleting the PVC leaves the underlying AWS EBS volume intact in AWS EC2.
# If you wish to delete the AWS EBS volume and avoid cloud storage charges:
aws ec2 describe-volumes \
  --filters "Name=tag:kubernetes.io/created-for/pvc/namespace,Values=$NAMESPACE" \
  --query "Volumes[*].VolumeId" \
  --output text | xargs -n 1 aws ec2 delete-volume --volume-id
```
