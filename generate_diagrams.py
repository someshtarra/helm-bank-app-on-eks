#!/usr/bin/env python3
"""
Generate professional, publication-quality DevOps architecture diagrams
for Bank Application on AWS EKS portfolio repository.
Outputs both 300 DPI PNG and vector SVG formats.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch

os.makedirs('diagrams', exist_ok=True)

# Common Palette
COLOR_BG = '#F8FAFC'
COLOR_BORDER = '#CBD5E1'
COLOR_AWS = '#FF9900'
COLOR_K8S = '#326CE5'
COLOR_SECURITY = '#00897B'
COLOR_METRICS = '#7E57C2'
COLOR_STORAGE = '#2E7D32'
COLOR_ERROR = '#D32F2F'
COLOR_CARD_BG = '#FFFFFF'
COLOR_TEXT_MAIN = '#0F172A'
COLOR_TEXT_MUTED = '#475569'

def create_box(ax, x, y, w, h, title, subtitle="", color=COLOR_K8S, bg=COLOR_CARD_BG, lw=2):
    # Shadow
    shadow = FancyBboxPatch((x + 0.008, y - 0.008), w, h, boxstyle="round,pad=0.015,rounding_size=0.02",
                            facecolor='#E2E8F0', edgecolor='none', zorder=1)
    ax.add_patch(shadow)
    # Main Box
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.02",
                         facecolor=bg, edgecolor=color, linewidth=lw, zorder=2)
    ax.add_patch(box)
    
    # Title badge / banner
    if subtitle:
        ax.text(x + w/2, y + h*0.62, title, ha='center', va='center',
                fontsize=11, fontweight='bold', color=COLOR_TEXT_MAIN, zorder=3)
        ax.text(x + w/2, y + h*0.32, subtitle, ha='center', va='center',
                fontsize=8.5, color=COLOR_TEXT_MUTED, zorder=3)
    else:
        ax.text(x + w/2, y + h/2, title, ha='center', va='center',
                fontsize=10.5, fontweight='bold', color=COLOR_TEXT_MAIN, zorder=3)

def draw_arrow(ax, x1, y1, x2, y2, label="", color='#64748B', style='->', lw=2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw, shrinkA=3, shrinkB=3),
                zorder=4)
    if label:
        mx, my = (x1 + x2)/2, (y1 + y2)/2
        ax.text(mx, my + 0.02, label, ha='center', va='bottom', fontsize=8,
                fontweight='semibold', color=COLOR_TEXT_MUTED,
                bbox=dict(boxstyle="round,pad=0.2", facecolor=COLOR_BG, edgecolor='none', alpha=0.85),
                zorder=5)

# ==============================================================================
# Diagram 1: Full Architecture
# ==============================================================================
def draw_architecture():
    fig, ax = plt.subplots(figsize=(14, 9), dpi=300)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Title
    ax.text(0.5, 0.96, "Bank Application on AWS EKS — End-to-End Architecture",
            ha='center', va='center', fontsize=17, fontweight='bold', color=COLOR_TEXT_MAIN)
    ax.text(0.5, 0.925, "Production Topology: Ingress, Horizontal Scaling, RBAC, and Persistent Storage",
            ha='center', va='center', fontsize=10.5, color=COLOR_TEXT_MUTED)

    # Big EKS Cluster Boundary
    eks_cluster = FancyBboxPatch((0.05, 0.05), 0.90, 0.68, boxstyle="round,pad=0.02,rounding_size=0.03",
                                 facecolor='#F1F5F9', edgecolor=COLOR_K8S, linewidth=2, linestyle='--', zorder=1)
    ax.add_patch(eks_cluster)
    ax.text(0.08, 0.705, "AWS EKS Cluster (VPC Subnets & NodeGroups)", fontsize=11, fontweight='bold', color=COLOR_K8S)

    # Top Flow: Internet -> AWS NLB -> Service
    create_box(ax, 0.40, 0.82, 0.20, 0.065, "End Users / Clients", "HTTPS / Port 80 Traffic", color='#64748B')
    create_box(ax, 0.40, 0.71, 0.20, 0.075, "AWS Network LB", "Layer 4 Cross-Zone NLB", color=COLOR_AWS, bg='#FFFBEB')
    draw_arrow(ax, 0.50, 0.82, 0.50, 0.785, "Internet")

    create_box(ax, 0.40, 0.58, 0.20, 0.075, "K8s Service (bank-app)", "Type: LoadBalancer / Port 80", color=COLOR_K8S)
    draw_arrow(ax, 0.50, 0.71, 0.50, 0.655, "NodePort / TargetGroup")

    # Pods Row
    pod_w, pod_h = 0.18, 0.12
    create_box(ax, 0.15, 0.38, pod_w, pod_h, "Bank Pod #1", "Apache httpd (UID 10001)\nProbes & Requests Active", color=COLOR_K8S)
    create_box(ax, 0.41, 0.38, pod_w, pod_h, "Bank Pod #2", "Apache httpd (UID 10001)\nProbes & Requests Active", color=COLOR_K8S)
    create_box(ax, 0.67, 0.38, pod_w, pod_h, "Bank Pod #N (Up to 10)", "Autoscaled via HPA\nTarget: 50% CPU", color=COLOR_K8S)

    # Routing from Service to Pods
    draw_arrow(ax, 0.45, 0.58, 0.24, 0.50, "kube-proxy")
    draw_arrow(ax, 0.50, 0.58, 0.50, 0.50, "Round-Robin")
    draw_arrow(ax, 0.55, 0.58, 0.76, 0.50, "Endpoints")

    # Bottom Flow: Storage
    create_box(ax, 0.40, 0.22, 0.20, 0.07, "PersistentVolumeClaim", "5Gi gp3 (ReadWriteOnce)", color=COLOR_STORAGE, bg='#F0FDF4')
    create_box(ax, 0.40, 0.10, 0.20, 0.07, "AWS EBS gp3 Volume", "AWS EBS CSI Driver (ext4)", color=COLOR_AWS, bg='#FFFBEB')

    draw_arrow(ax, 0.24, 0.38, 0.44, 0.29, "VolumeMount")
    draw_arrow(ax, 0.50, 0.38, 0.50, 0.29, "Node 1 Lock")
    draw_arrow(ax, 0.50, 0.22, 0.50, 0.17, "Dynamic Provision")

    # Left: RBAC Panel
    create_box(ax, 0.08, 0.18, 0.19, 0.15, "RBAC Governance", "ServiceAccount: bank-app\nRole: Least Privilege (ReadOnly)\nautomountToken: false", color=COLOR_SECURITY, bg='#F0FDFA')
    draw_arrow(ax, 0.17, 0.33, 0.20, 0.38, "Binds SA", color=COLOR_SECURITY)

    # Right: HPA & Metrics Panel
    create_box(ax, 0.73, 0.18, 0.19, 0.15, "Autoscaling (HPA v2)", "Metrics Server Scraping\nTarget: 50% CPU / 80% Mem\nMin: 2 | Max: 10 Replicas", color=COLOR_METRICS, bg='#FAF5FF')
    draw_arrow(ax, 0.78, 0.33, 0.76, 0.38, "Scales Pods", color=COLOR_METRICS)

    plt.tight_layout()
    fig.savefig('diagrams/architecture.png', dpi=300, facecolor=COLOR_BG)
    fig.savefig('diagrams/architecture.svg', facecolor=COLOR_BG)
    plt.close()
    print("Generated architecture.png and architecture.svg")

# ==============================================================================
# Diagram 2: HPA Scaling Flow
# ==============================================================================
def draw_hpa():
    fig, ax = plt.subplots(figsize=(13, 7.5), dpi=300)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    ax.text(0.5, 0.95, "Horizontal Pod Autoscaler (HPA v2) — Scaling Mechanics",
            ha='center', va='center', fontsize=17, fontweight='bold', color=COLOR_TEXT_MAIN)
    ax.text(0.5, 0.90, "Telemetry Collection, Mathematical Target Evaluation, and Stabilization Behavior",
            ha='center', va='center', fontsize=10.5, color=COLOR_TEXT_MUTED)

    # Step 1: Kubelet / cAdvisor
    create_box(ax, 0.06, 0.65, 0.22, 0.14, "1. Kubelet / cAdvisor", "Scrapes Pod cgroups\nCalculates millicores vs\nrequests.cpu (200m)", color=COLOR_K8S)
    
    # Step 2: Metrics Server
    create_box(ax, 0.39, 0.65, 0.22, 0.14, "2. Metrics Server", "Aggregates cluster metrics\nExposes sub-API endpoint:\nmetrics.k8s.io", color=COLOR_METRICS, bg='#FAF5FF')
    draw_arrow(ax, 0.28, 0.72, 0.39, 0.72, "Scrape /metrics/resource", color=COLOR_METRICS)

    # Step 3: HPA Controller
    create_box(ax, 0.72, 0.65, 0.22, 0.14, "3. HPA v2 Controller", "Evaluates every 15s:\nDesired = ceil(Current * Util/50%)\nStabilization: 300s scaleDown", color=COLOR_METRICS, bg='#FAF5FF')
    draw_arrow(ax, 0.61, 0.72, 0.72, 0.72, "Query API", color=COLOR_METRICS)

    # Step 4: Deployment PATCH
    create_box(ax, 0.72, 0.35, 0.22, 0.14, "4. Deployment Controller", "Receives PATCH:\nspec.replicas: 2 -> 4 -> 10\nZero-Downtime Rolling Update", color=COLOR_K8S)
    draw_arrow(ax, 0.83, 0.65, 0.83, 0.49, "PATCH replicas", color=COLOR_K8S)

    # Step 5: Visual Pod Scaling progression
    ax.text(0.40, 0.44, "Dynamic Pod Scale Range (Min: 2 → Max: 10 Replicas)",
            ha='center', va='center', fontsize=11, fontweight='bold', color=COLOR_TEXT_MAIN)
    
    # Boxes showing progression
    scale_steps = ["1-2 Pods\nBaseline (50m)", "4 Pods\nModerate (350m)", "7 Pods\nHigh Load (700m)", "10 Pods (Max)\nPeak Surges (1000m+)"]
    x_starts = [0.06, 0.22, 0.38, 0.54]
    for i, (st, xs) in enumerate(zip(scale_steps, x_starts)):
        create_box(ax, xs, 0.26, 0.14, 0.13, f"Scale Phase {i+1}", st, color=COLOR_K8S if i<3 else COLOR_AWS, bg='#F8FAFC')
        if i < 3:
            draw_arrow(ax, xs + 0.14, 0.325, xs + 0.16, 0.325, "", color='#94A3B8')

    # Draw arrow from Deployment to Scale Phase 4
    draw_arrow(ax, 0.72, 0.39, 0.68, 0.325, "Spawns Pods", color=COLOR_K8S)

    # Mathematical Formula Callout
    formula_box = FancyBboxPatch((0.06, 0.05), 0.88, 0.14, boxstyle="round,pad=0.015,rounding_size=0.02",
                                 facecolor='#EFF6FF', edgecolor='#93C5FD', linewidth=1.5, zorder=2)
    ax.add_patch(formula_box)
    ax.text(0.50, 0.135, "CRITICAL EDUCATIONAL PRINCIPLE: Why CPU Requests Are Mandatory",
            ha='center', va='center', fontsize=10.5, fontweight='bold', color='#1E40AF')
    ax.text(0.50, 0.085, "Utilization % = (Actual CPU Millicores / Requested CPU Millicores) * 100\nWithout 'resources.requests.cpu: 200m', HPA cannot compute utilization percentage and remains <unknown>/50%!",
            ha='center', va='center', fontsize=9.5, color='#1E3A8A')

    plt.tight_layout()
    fig.savefig('diagrams/hpa-flow.png', dpi=300, facecolor=COLOR_BG)
    fig.savefig('diagrams/hpa-flow.svg', facecolor=COLOR_BG)
    plt.close()
    print("Generated hpa-flow.png and hpa-flow.svg")

# ==============================================================================
# Diagram 3: Storage Flow & RWO Conflict
# ==============================================================================
def draw_storage():
    fig, ax = plt.subplots(figsize=(14, 8.5), dpi=300)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    ax.text(0.5, 0.96, "Storage Architecture: AWS EBS ReadWriteOnce (RWO) Dilemma vs. AWS EFS",
            ha='center', va='center', fontsize=16, fontweight='bold', color=COLOR_TEXT_MAIN)
    ax.text(0.5, 0.92, "Why Horizontally Scaled Deployments Cannot Safely Share a Single EBS Volume",
            ha='center', va='center', fontsize=10.5, color=COLOR_TEXT_MUTED)

    # Left Side: The Problem (EBS RWO with 2 Nodes)
    left_bg = FancyBboxPatch((0.04, 0.05), 0.43, 0.83, boxstyle="round,pad=0.02,rounding_size=0.02",
                             facecolor='#FEF2F2', edgecolor='#FCA5A5', linewidth=1.5, zorder=1)
    ax.add_patch(left_bg)
    ax.text(0.255, 0.84, "CURRENT ARCHITECTURE: AWS EBS (ReadWriteOnce)", ha='center', fontsize=11.5, fontweight='bold', color=COLOR_ERROR)

    create_box(ax, 0.07, 0.68, 0.17, 0.11, "Pod 1 (Worker Node A)", "Scheduled on Node A\nMounts /var/www/html/", color=COLOR_K8S)
    create_box(ax, 0.27, 0.68, 0.17, 0.11, "Pod 2 (Worker Node B)", "Scheduled on Node B\nAttempts volume mount", color=COLOR_ERROR, bg='#FFF1F2')

    create_box(ax, 0.15, 0.49, 0.21, 0.09, "Single PVC (ebs-pvc)", "accessModes: [ReadWriteOnce]\nstorage: 5Gi gp3", color=COLOR_STORAGE, bg='#F0FDF4')
    create_box(ax, 0.15, 0.34, 0.21, 0.09, "AWS EBS CSI Driver", "volumeBindingMode:\nWaitForFirstConsumer", color=COLOR_AWS, bg='#FFFBEB')
    create_box(ax, 0.15, 0.19, 0.21, 0.09, "AWS EBS gp3 Volume", "Block Storage (Single Node)\nLocked to Node A (AZ-1a)", color=COLOR_AWS, bg='#FFFBEB')

    draw_arrow(ax, 0.155, 0.68, 0.22, 0.58, "Attached", color=COLOR_STORAGE)
    draw_arrow(ax, 0.355, 0.68, 0.28, 0.58, "ATTACH ERROR!", color=COLOR_ERROR)
    draw_arrow(ax, 0.255, 0.49, 0.255, 0.43, "Dynamic Provision", color=COLOR_STORAGE)
    draw_arrow(ax, 0.255, 0.34, 0.255, 0.28, "Attach to Node A", color=COLOR_AWS)

    # Warning Box
    ax.text(0.255, 0.11, "MULTI-ATTACH FAILURE:\nEBS volumes can only attach to 1 EC2 instance.\nPod 2 on Node B gets stuck in ContainerCreating!",
            ha='center', va='center', fontsize=8.5, fontweight='bold', color=COLOR_ERROR,
            bbox=dict(boxstyle="round,pad=0.3", facecolor='#FEE2E2', edgecolor=COLOR_ERROR, lw=1))

    # Right Side: The Solution (AWS EFS RWX or Stateless)
    right_bg = FancyBboxPatch((0.53, 0.05), 0.43, 0.83, boxstyle="round,pad=0.02,rounding_size=0.02",
                              facecolor='#F0FDF4', edgecolor='#86EFAC', linewidth=1.5, zorder=1)
    ax.add_patch(right_bg)
    ax.text(0.745, 0.84, "RECOMMENDED SOLUTION: AWS EFS (ReadWriteMany)", ha='center', fontsize=11.5, fontweight='bold', color=COLOR_STORAGE)

    create_box(ax, 0.56, 0.68, 0.17, 0.11, "Pod 1 (Worker Node A)", "Mounts /var/www/html/\nConcurrent Read/Write", color=COLOR_K8S)
    create_box(ax, 0.76, 0.68, 0.17, 0.11, "Pod 2 (Worker Node B)", "Mounts /var/www/html/\nConcurrent Read/Write", color=COLOR_K8S)

    create_box(ax, 0.64, 0.49, 0.21, 0.09, "EFS PVC (efs-pvc)", "accessModes: [ReadWriteMany]\nShared Network File System", color=COLOR_STORAGE, bg='#F0FDF4')
    create_box(ax, 0.64, 0.34, 0.21, 0.09, "AWS EFS CSI Driver", "Mounts via NFSv4.1 Protocol\nCross-AZ Elastic Targets", color=COLOR_AWS, bg='#FFFBEB')
    create_box(ax, 0.64, 0.19, 0.21, 0.09, "AWS EFS FileSystem", "Multi-AZ Managed NFS\nConcurrently shared by 1000+ Pods", color=COLOR_STORAGE, bg='#DCFCE7')

    draw_arrow(ax, 0.645, 0.68, 0.71, 0.58, "NFS Mount", color=COLOR_STORAGE)
    draw_arrow(ax, 0.845, 0.68, 0.77, 0.58, "NFS Mount", color=COLOR_STORAGE)
    draw_arrow(ax, 0.745, 0.49, 0.745, 0.43, "Dynamic Provision", color=COLOR_STORAGE)
    draw_arrow(ax, 0.745, 0.34, 0.745, 0.28, "Mount Targets", color=COLOR_AWS)

    # Success Box
    ax.text(0.745, 0.11, "PRODUCTION READINESS:\nEFS allows all HPA replicas (1 to 10) across all\nAZs and nodes to share storage without conflict!",
            ha='center', va='center', fontsize=8.5, fontweight='bold', color=COLOR_STORAGE,
            bbox=dict(boxstyle="round,pad=0.3", facecolor='#DCFCE7', edgecolor=COLOR_STORAGE, lw=1))

    plt.tight_layout()
    fig.savefig('diagrams/storage-flow.png', dpi=300, facecolor=COLOR_BG)
    fig.savefig('diagrams/storage-flow.svg', facecolor=COLOR_BG)
    plt.close()
    print("Generated storage-flow.png and storage-flow.svg")

# ==============================================================================
# Diagram 4: RBAC Flow & Least Privilege
# ==============================================================================
def draw_rbac():
    fig, ax = plt.subplots(figsize=(13, 7.5), dpi=300)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    ax.text(0.5, 0.95, "Kubernetes RBAC Architecture & Least-Privilege Implementation",
            ha='center', va='center', fontsize=17, fontweight='bold', color=COLOR_TEXT_MAIN)
    ax.text(0.5, 0.90, "Securing API Server Access: ServiceAccounts, Roles, and RoleBindings",
            ha='center', va='center', fontsize=10.5, color=COLOR_TEXT_MUTED)

    # 4-step Horizontal Flow
    box_w, box_h = 0.19, 0.18
    y_pos = 0.52

    create_box(ax, 0.05, y_pos, box_w, box_h, "1. Bank App Pod", "Specifies:\nserviceAccountName:\nbank-app\nautomountToken: false", color=COLOR_K8S)
    create_box(ax, 0.29, y_pos, box_w, box_h, "2. ServiceAccount", "Identity for pod in K8s\nNamespace: {{ .Release.Namespace }}\nOptional IRSA annotations", color=COLOR_SECURITY, bg='#F0FDFA')
    create_box(ax, 0.53, y_pos, box_w, box_h, "3. RoleBinding", "Binds Subject to Role\nCorrect Syntax: roleRef is a map\napiGroup: rbac.authorization.k8s.io", color=COLOR_SECURITY, bg='#F0FDFA')
    create_box(ax, 0.77, y_pos, box_w, box_h, "4. Scoped Role", "Defines Allowed Verbs:\nresources: ['configmaps']\nverbs: ['get', 'list', 'watch']", color=COLOR_SECURITY, bg='#F0FDFA')

    draw_arrow(ax, 0.24, y_pos + box_h/2, 0.29, y_pos + box_h/2, "Assumes SA", color=COLOR_SECURITY)
    draw_arrow(ax, 0.48, y_pos + box_h/2, 0.53, y_pos + box_h/2, "Referenced in subjects", color=COLOR_SECURITY)
    draw_arrow(ax, 0.72, y_pos + box_h/2, 0.77, y_pos + box_h/2, "Points to roleRef", color=COLOR_SECURITY)

    # Comparison Callout at Bottom
    comp_box = FancyBboxPatch((0.05, 0.08), 0.91, 0.35, boxstyle="round,pad=0.015,rounding_size=0.02",
                              facecolor='#FFFFFF', edgecolor=COLOR_BORDER, linewidth=1.5, zorder=2)
    ax.add_patch(comp_box)

    ax.text(0.50, 0.38, "CRITICAL AUDIT: Original RBAC Flaws vs. Hardened Production Fixes",
            ha='center', va='center', fontsize=11.5, fontweight='bold', color=COLOR_TEXT_MAIN)

    # Left: Original Flaws
    ax.text(0.27, 0.24, "Vulnerable Original Configuration:\n• Namespace Mismatch: Role in 'lab', SA in 'default'\n• Invalid Syntax: roleRef written as a list with 'apiGroups'\n• Privilege Escalation: Full CRUD on pods (delete, create, patch)\n  Allows compromised web server to delete cluster pods!",
            ha='center', va='center', fontsize=9, color=COLOR_ERROR,
            bbox=dict(boxstyle="round,pad=0.3", facecolor='#FEF2F2', edgecolor='#FCA5A5'))

    # Right: Hardened Fix
    ax.text(0.73, 0.24, "Hardened Production Implementation:\n• Consistent Scope: All resources use {{ .Release.Namespace }}\n• Schema Compliant: roleRef is a map with singular apiGroup\n• Least Privilege: Read-only access to ConfigMaps only\n• Token Hardening: automountServiceAccountToken: false",
            ha='center', va='center', fontsize=9, color=COLOR_STORAGE,
            bbox=dict(boxstyle="round,pad=0.3", facecolor='#F0FDF4', edgecolor='#86EFAC'))

    plt.tight_layout()
    fig.savefig('diagrams/rbac-flow.png', dpi=300, facecolor=COLOR_BG)
    fig.savefig('diagrams/rbac-flow.svg', facecolor=COLOR_BG)
    plt.close()
    print("Generated rbac-flow.png and rbac-flow.svg")

if __name__ == '__main__':
    draw_architecture()
    draw_hpa()
    draw_storage()
    draw_rbac()
    print("All diagrams generated successfully!")
