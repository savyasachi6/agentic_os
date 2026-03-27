"""
Alerting and metrics monitoring for DevOps automation.
"""
import operator
from typing import Dict, List
from .models import AlertRule


def evaluate_metrics(rules: List[AlertRule], current_values: Dict[str, float]) -> List[str]:
    """
    Evaluates a set of alert rules against current metric values.
    Returns a list of alert messages for triggered rules.
    """
    alerts = []
    ops = {
        ">": operator.gt,
        "<": operator.lt,
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
    }

    for rule in rules:
        if rule.metric_name in current_values:
            val = current_values[rule.metric_name]
            compare_func = ops.get(rule.comparison)
            if compare_func and compare_func(val, rule.threshold):
                msg = f"ALERT [{rule.action}]: {rule.metric_name} is {val} (threshold {rule.comparison} {rule.threshold})"
                alerts.append(msg)
                
    return alerts


class MetricsWatcher:
    """
    Periodic thread that polls metrics and fires alerts.
    (Simplified stub for implementation plan).
    """
    def __init__(self, rules: List[AlertRule], poll_interval: int = 60):
        self.rules = rules
        self.poll_interval = poll_interval
        self.is_running = False

    def start(self, poll_fn):
        """Mock start loop."""
        print(f"Starting MetricsWatcher with {len(self.rules)} rules...")
        self.is_running = True
        # In a real implementation, this would be a Thread or asyncio Task.
        
    def stop(self):
        self.is_running = False
        print("MetricsWatcher stopped.")
