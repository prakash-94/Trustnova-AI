"""
Comprehensive XGBoost Fraud Detection Model Evaluation & Visualization.

Generates:
1. Confusion Matrix Heatmap
2. ROC Curve
3. Precision-Recall Curve
4. Feature Importance Bar Chart
5. Fraud Probability Distribution
6. Classification Report
7. Cross-Validation Results
8. Threshold Analysis
"""
import os
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import seaborn as sns

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import (
    precision_recall_curve,
    roc_curve,
    auc,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    accuracy_score,
)
from imblearn.over_sampling import SMOTE
import xgboost as xgb

# --- Configuration ---
FEATURE_COLS = [
    "amount", "hour", "geo_mismatch", "device_new",
    "amount_zscore", "velocity_30m", "credit_score",
    "account_age_days", "is_weekend",
]
TARGET_COL = "is_fraud"
OUTPUT_DIR = "reports"

# Styling
plt.style.use('seaborn-v0_8-darkgrid')
COLORS = {
    'primary': '#6366f1',
    'secondary': '#8b5cf6', 
    'accent': '#ec4899',
    'success': '#10b981',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'bg_dark': '#0f172a',
    'bg_card': '#1e293b',
    'text': '#e2e8f0',
    'text_dim': '#94a3b8',
}


def load_and_prepare_data():
    """Load data, split, and apply SMOTE."""
    df = pd.read_csv("data/processed/enriched_transactions.csv")
    X = df[FEATURE_COLS].fillna(0)
    y = df[TARGET_COL]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # SMOTE
    n_fraud = y_train.sum()
    n_non_fraud = len(y_train) - n_fraud
    target_fraud = int(0.10 * n_non_fraud / 0.90)

    smote = SMOTE(
        sampling_strategy={1: target_fraud},
        random_state=42,
        k_neighbors=min(5, int(n_fraud) - 1)
    )
    X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)

    return df, X_train, X_test, y_train, y_test, X_train_smote, y_train_smote


def train_and_evaluate(X_train, y_train, X_test, y_test):
    """Train XGBoost and return predictions."""
    scale_pos_weight = (len(y_train) - y_train.sum()) / y_train.sum()
    
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.1,
        scale_pos_weight=scale_pos_weight, objective="binary:logistic",
        eval_metric="aucpr", random_state=42, use_label_encoder=False,
        min_child_weight=3, subsample=0.8, colsample_bytree=0.8, gamma=0.1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    return model, y_pred, y_prob


def run_cross_validation(X, y):
    """Run stratified 5-fold cross-validation."""
    # Apply SMOTE inside each fold
    from imblearn.pipeline import Pipeline as ImbPipeline
    
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.1,
        objective="binary:logistic", eval_metric="aucpr",
        random_state=42, use_label_encoder=False,
        min_child_weight=3, subsample=0.8, colsample_bytree=0.8, gamma=0.1,
    )

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    cv_results = {
        'fold': [], 'pr_auc': [], 'roc_auc': [], 'f1': [],
        'precision': [], 'recall': [], 'accuracy': []
    }

    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y), 1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # SMOTE on training fold only
        n_fraud = y_tr.sum()
        n_non_fraud = len(y_tr) - n_fraud
        target_fraud = int(0.10 * n_non_fraud / 0.90)
        
        if target_fraud > n_fraud:
            smote = SMOTE(sampling_strategy={1: target_fraud}, random_state=42,
                         k_neighbors=min(5, int(n_fraud) - 1))
            X_tr, y_tr = smote.fit_resample(X_tr, y_tr)

        model.fit(X_tr, y_tr, verbose=False)
        y_val_prob = model.predict_proba(X_val)[:, 1]
        y_val_pred = model.predict(X_val)

        prec, rec, _ = precision_recall_curve(y_val, y_val_prob)
        
        cv_results['fold'].append(fold)
        cv_results['pr_auc'].append(auc(rec, prec))
        cv_results['roc_auc'].append(roc_auc_score(y_val, y_val_prob))
        cv_results['f1'].append(f1_score(y_val, y_val_pred))
        cv_results['precision'].append(precision_score(y_val, y_val_pred))
        cv_results['recall'].append(recall_score(y_val, y_val_pred))
        cv_results['accuracy'].append(accuracy_score(y_val, y_val_pred))

    return pd.DataFrame(cv_results)


def plot_all_visualizations(model, X_test, y_test, y_pred, y_prob, cv_results, df):
    """Generate the comprehensive visualization dashboard."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ========== FIGURE 1: Main Dashboard (2x2) ==========
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    fig.patch.set_facecolor(COLORS['bg_dark'])
    fig.suptitle('XGBoost Fraud Detection — Model Performance Dashboard',
                 fontsize=18, fontweight='bold', color=COLORS['text'], y=0.98)

    # --- 1. Confusion Matrix ---
    ax = axes[0, 0]
    ax.set_facecolor(COLORS['bg_card'])
    cm = confusion_matrix(y_test, y_pred)
    labels = np.array([[f"TN\n{cm[0,0]}", f"FP\n{cm[0,1]}"],
                       [f"FN\n{cm[1,0]}", f"TP\n{cm[1,1]}"]])
    
    sns.heatmap(cm, annot=labels, fmt='', cmap='RdYlGn_r', ax=ax,
                xticklabels=['Not Fraud', 'Fraud'],
                yticklabels=['Not Fraud', 'Fraud'],
                cbar_kws={'label': 'Count'},
                linewidths=2, linecolor=COLORS['bg_dark'],
                annot_kws={'size': 14, 'fontweight': 'bold'})
    ax.set_title('Confusion Matrix', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('Predicted', fontsize=11, color=COLORS['text_dim'])
    ax.set_ylabel('Actual', fontsize=11, color=COLORS['text_dim'])
    ax.tick_params(colors=COLORS['text_dim'])

    # --- 2. ROC Curve ---
    ax = axes[0, 1]
    ax.set_facecolor(COLORS['bg_card'])
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc_val = roc_auc_score(y_test, y_prob)
    
    ax.plot(fpr, tpr, color=COLORS['primary'], lw=2.5,
            label=f'ROC Curve (AUC = {roc_auc_val:.4f})')
    ax.fill_between(fpr, tpr, alpha=0.15, color=COLORS['primary'])
    ax.plot([0, 1], [0, 1], 'k--', lw=1, alpha=0.5, label='Random Baseline')
    ax.set_title('ROC Curve', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('False Positive Rate', fontsize=11, color=COLORS['text_dim'])
    ax.set_ylabel('True Positive Rate', fontsize=11, color=COLORS['text_dim'])
    ax.legend(loc='lower right', fontsize=10, framealpha=0.8)
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, alpha=0.2)

    # --- 3. Precision-Recall Curve ---
    ax = axes[1, 0]
    ax.set_facecolor(COLORS['bg_card'])
    precision, recall, thresholds = precision_recall_curve(y_test, y_prob)
    pr_auc_val = auc(recall, precision)
    ap = average_precision_score(y_test, y_prob)
    
    ax.plot(recall, precision, color=COLORS['accent'], lw=2.5,
            label=f'PR Curve (AUC = {pr_auc_val:.4f})')
    ax.fill_between(recall, precision, alpha=0.15, color=COLORS['accent'])
    baseline = y_test.mean()
    ax.axhline(y=baseline, color=COLORS['warning'], linestyle='--', lw=1,
               label=f'Baseline (fraud rate = {baseline:.3f})')
    ax.set_title('Precision-Recall Curve', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('Recall', fontsize=11, color=COLORS['text_dim'])
    ax.set_ylabel('Precision', fontsize=11, color=COLORS['text_dim'])
    ax.legend(loc='upper right', fontsize=10, framealpha=0.8)
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, alpha=0.2)

    # --- 4. Feature Importance ---
    ax = axes[1, 1]
    ax.set_facecolor(COLORS['bg_card'])
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)
    
    colors_bars = plt.cm.viridis(np.linspace(0.3, 0.9, len(sorted_idx)))
    ax.barh(range(len(sorted_idx)), importances[sorted_idx], color=colors_bars, edgecolor='none', height=0.7)
    ax.set_yticks(range(len(sorted_idx)))
    ax.set_yticklabels([FEATURE_COLS[i] for i in sorted_idx], fontsize=10, color=COLORS['text'])
    ax.set_title('Feature Importance', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('Importance Score', fontsize=11, color=COLORS['text_dim'])
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, axis='x', alpha=0.2)
    
    # Add value labels
    for i, (idx, imp) in enumerate(zip(sorted_idx, importances[sorted_idx])):
        ax.text(imp + 0.005, i, f'{imp:.3f}', va='center', fontsize=9, color=COLORS['text'])

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path1 = os.path.join(OUTPUT_DIR, "xgboost_dashboard.png")
    fig.savefig(path1, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Saved: {path1}")

    # ========== FIGURE 2: Deep Dive Analysis (2x2) ==========
    fig2, axes2 = plt.subplots(2, 2, figsize=(16, 14))
    fig2.patch.set_facecolor(COLORS['bg_dark'])
    fig2.suptitle('XGBoost Fraud Detection — Deep Dive Analysis',
                  fontsize=18, fontweight='bold', color=COLORS['text'], y=0.98)

    # --- 5. Fraud Probability Distribution ---
    ax = axes2[0, 0]
    ax.set_facecolor(COLORS['bg_card'])
    
    fraud_probs = y_prob[y_test == 1]
    legit_probs = y_prob[y_test == 0]
    
    ax.hist(legit_probs, bins=50, alpha=0.7, color=COLORS['success'], label=f'Legitimate (n={len(legit_probs)})', density=True)
    ax.hist(fraud_probs, bins=50, alpha=0.7, color=COLORS['danger'], label=f'Fraud (n={len(fraud_probs)})', density=True)
    ax.axvline(x=0.5, color=COLORS['warning'], linestyle='--', lw=2, label='Decision Threshold (0.5)')
    ax.set_title('Fraud Probability Distribution', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('Predicted Fraud Probability', fontsize=11, color=COLORS['text_dim'])
    ax.set_ylabel('Density', fontsize=11, color=COLORS['text_dim'])
    ax.legend(fontsize=9, framealpha=0.8)
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, alpha=0.2)

    # --- 6. Cross-Validation Results ---
    ax = axes2[0, 1]
    ax.set_facecolor(COLORS['bg_card'])
    
    metrics_to_plot = ['pr_auc', 'roc_auc', 'f1', 'precision', 'recall']
    x_pos = np.arange(len(metrics_to_plot))
    means = [cv_results[m].mean() for m in metrics_to_plot]
    stds = [cv_results[m].std() for m in metrics_to_plot]
    
    bars = ax.bar(x_pos, means, yerr=stds, capsize=5,
                  color=[COLORS['primary'], COLORS['secondary'], COLORS['accent'],
                         COLORS['success'], COLORS['warning']],
                  edgecolor='none', alpha=0.85, width=0.6)
    
    ax.set_xticks(x_pos)
    ax.set_xticklabels(['PR-AUC', 'ROC-AUC', 'F1', 'Precision', 'Recall'],
                       fontsize=10, color=COLORS['text'])
    ax.set_ylim(0, 1.15)
    ax.set_title('5-Fold Cross-Validation Results', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_ylabel('Score', fontsize=11, color=COLORS['text_dim'])
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, axis='y', alpha=0.2)
    
    for bar, mean, std in zip(bars, means, stds):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + std + 0.02,
                f'{mean:.3f}\n+/-{std:.3f}', ha='center', va='bottom',
                fontsize=9, fontweight='bold', color=COLORS['text'])

    # --- 7. Threshold Analysis ---
    ax = axes2[1, 0]
    ax.set_facecolor(COLORS['bg_card'])
    
    thresholds_range = np.arange(0.1, 0.95, 0.05)
    f1_scores = []
    prec_scores = []
    rec_scores = []
    
    for t in thresholds_range:
        y_pred_t = (y_prob >= t).astype(int)
        f1_scores.append(f1_score(y_test, y_pred_t, zero_division=0))
        prec_scores.append(precision_score(y_test, y_pred_t, zero_division=0))
        rec_scores.append(recall_score(y_test, y_pred_t, zero_division=0))
    
    ax.plot(thresholds_range, f1_scores, '-o', color=COLORS['accent'], lw=2, markersize=4, label='F1 Score')
    ax.plot(thresholds_range, prec_scores, '-s', color=COLORS['success'], lw=2, markersize=4, label='Precision')
    ax.plot(thresholds_range, rec_scores, '-^', color=COLORS['warning'], lw=2, markersize=4, label='Recall')
    
    best_f1_idx = np.argmax(f1_scores)
    ax.axvline(x=thresholds_range[best_f1_idx], color=COLORS['danger'], linestyle='--', lw=1.5,
               label=f'Best F1 threshold = {thresholds_range[best_f1_idx]:.2f}')
    
    ax.set_title('Threshold Analysis', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.set_xlabel('Classification Threshold', fontsize=11, color=COLORS['text_dim'])
    ax.set_ylabel('Score', fontsize=11, color=COLORS['text_dim'])
    ax.legend(fontsize=9, framealpha=0.8)
    ax.tick_params(colors=COLORS['text_dim'])
    ax.grid(True, alpha=0.2)

    # --- 8. Per-Fold CV Heatmap ---
    ax = axes2[1, 1]
    ax.set_facecolor(COLORS['bg_card'])
    
    cv_heatmap = cv_results[['pr_auc', 'roc_auc', 'f1', 'precision', 'recall']].T
    cv_heatmap.columns = [f'Fold {i+1}' for i in range(len(cv_heatmap.columns))]
    
    sns.heatmap(cv_heatmap, annot=True, fmt='.3f', cmap='YlGnBu', ax=ax,
                linewidths=1, linecolor=COLORS['bg_dark'],
                annot_kws={'size': 11, 'fontweight': 'bold'},
                cbar_kws={'label': 'Score'})
    ax.set_title('Per-Fold Performance Heatmap', fontsize=14, fontweight='bold', color=COLORS['text'], pad=10)
    ax.tick_params(colors=COLORS['text_dim'])
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path2 = os.path.join(OUTPUT_DIR, "xgboost_deep_dive.png")
    fig2.savefig(path2, dpi=150, bbox_inches='tight', facecolor=fig2.get_facecolor())
    plt.close()
    print(f"  Saved: {path2}")

    return path1, path2


def print_detailed_report(y_test, y_pred, y_prob, cv_results):
    """Print a comprehensive text report."""
    print("\n" + "=" * 70)
    print("XGBOOST FRAUD DETECTION — COMPREHENSIVE EVALUATION REPORT")
    print("=" * 70)

    # Classification Report
    print("\n1. CLASSIFICATION REPORT (Test Set)")
    print("-" * 50)
    print(classification_report(y_test, y_pred, target_names=["Legitimate", "Fraud"]))

    # Key Metrics
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    
    precision, recall, _ = precision_recall_curve(y_test, y_prob)
    pr_auc_val = auc(recall, precision)
    roc_auc_val = roc_auc_score(y_test, y_prob)

    print("2. KEY METRICS")
    print("-" * 50)
    print(f"  PR-AUC (Primary):       {pr_auc_val:.4f}  {'PASS (>0.85)' if pr_auc_val > 0.85 else 'FAIL (<0.85)'}")
    print(f"  ROC-AUC:                {roc_auc_val:.4f}")
    print(f"  F1 Score:               {f1_score(y_test, y_pred):.4f}")
    print(f"  Accuracy:               {accuracy_score(y_test, y_pred):.4f}")
    print(f"  Precision:              {precision_score(y_test, y_pred):.4f}")
    print(f"  Recall:                 {recall_score(y_test, y_pred):.4f}")
    
    print("\n3. CONFUSION MATRIX BREAKDOWN")
    print("-" * 50)
    print(f"  True Negatives (TN):    {tn:,}  (legitimate correctly identified)")
    print(f"  True Positives (TP):    {tp:,}  (fraud correctly caught)")
    print(f"  False Positives (FP):   {fp:,}  (legitimate flagged as fraud)")
    print(f"  False Negatives (FN):   {fn:,}  (fraud missed by model)")
    print(f"  False Positive Rate:    {fp/(fp+tn):.4f}  ({fp/(fp+tn)*100:.2f}%)")
    print(f"  False Negative Rate:    {fn/(fn+tp):.4f}  ({fn/(fn+tp)*100:.2f}%)")

    # Cross-validation
    print("\n4. 5-FOLD CROSS-VALIDATION")
    print("-" * 50)
    for metric in ['pr_auc', 'roc_auc', 'f1', 'precision', 'recall']:
        mean = cv_results[metric].mean()
        std = cv_results[metric].std()
        print(f"  {metric:15s}  {mean:.4f} +/- {std:.4f}  (range: {cv_results[metric].min():.4f} - {cv_results[metric].max():.4f})")

    # Verdict
    print("\n5. ACCURACY VERDICT")
    print("-" * 50)
    
    issues = []
    if pr_auc_val < 0.85:
        issues.append("PR-AUC below target (0.85)")
    if fn > 0:
        issues.append(f"{fn} fraud transaction(s) missed (false negatives)")
    if fp > tp * 0.5:
        issues.append(f"High false positive rate ({fp} FP vs {tp} TP)")
    if cv_results['pr_auc'].std() > 0.05:
        issues.append(f"High CV variance (std={cv_results['pr_auc'].std():.4f})")
    
    # Check for overfitting
    cv_mean_pr_auc = cv_results['pr_auc'].mean()
    overfit_gap = pr_auc_val - cv_mean_pr_auc
    if overfit_gap > 0.1:
        issues.append(f"Possible overfitting: test PR-AUC ({pr_auc_val:.4f}) >> CV mean ({cv_mean_pr_auc:.4f})")
    
    if not issues:
        print("  VERDICT: MODEL IS ACCURATE AND RELIABLE")
        print("  - PR-AUC exceeds target (0.85)")
        print("  - Cross-validation is consistent")
        print("  - No significant overfitting detected")
        print("  - False negative rate is acceptable")
    else:
        print("  VERDICT: MODEL HAS POTENTIAL CONCERNS")
        for issue in issues:
            print(f"  [!] {issue}")
    
    # Additional context
    print(f"\n  Overfitting Check: Test PR-AUC={pr_auc_val:.4f}, CV Mean={cv_mean_pr_auc:.4f}, Gap={overfit_gap:.4f}")
    if overfit_gap <= 0.1:
        print("  -> No significant overfitting detected (gap <= 0.10)")
    else:
        print("  -> POTENTIAL overfitting detected (gap > 0.10)")
    
    print("\n" + "=" * 70)


def main():
    print("Loading and preparing data...")
    df, X_train, X_test, y_train, y_test, X_train_smote, y_train_smote = load_and_prepare_data()
    
    print("Training model...")
    model, y_pred, y_prob = train_and_evaluate(X_train_smote, y_train_smote, X_test, y_test)
    
    print("Running 5-fold cross-validation...")
    X_all = df[FEATURE_COLS].fillna(0)
    y_all = df[TARGET_COL]
    cv_results = run_cross_validation(X_all, y_all)
    
    print("Generating visualizations...")
    path1, path2 = plot_all_visualizations(model, X_test, y_test, y_pred, y_prob, cv_results, df)
    
    print_detailed_report(y_test, y_pred, y_prob, cv_results)
    
    print(f"\nVisualization files saved to '{OUTPUT_DIR}/' directory:")
    print(f"  1. {path1}")
    print(f"  2. {path2}")


if __name__ == "__main__":
    main()
