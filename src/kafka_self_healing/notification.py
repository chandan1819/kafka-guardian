"""
Notification system for the Kafka self-healing system.

This module provides the core notification framework including:
- NotificationService: Main notification orchestrator
- NotificationTemplate: Email content generation
- DeliveryQueue: Notification retry and queuing
- NotificationResult: Delivery result tracking
"""

import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from typing import List, Dict, Any, Optional, Callable, Union
import threading
import time
import queue
import logging
from string import Template

from .models import NodeConfig, RecoveryResult, NotificationConfig
from .exceptions import NotificationError


@dataclass
class NotificationResult:
    """Result of a notification delivery attempt."""
    notification_id: str
    recipient: str
    delivery_time: datetime
    success: bool
    error_message: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'notification_id': self.notification_id,
            'recipient': self.recipient,
            'delivery_time': self.delivery_time.isoformat(),
            'success': self.success,
            'error_message': self.error_message,
            'retry_count': self.retry_count
        }


@dataclass
class NotificationMessage:
    """A notification message to be delivered."""
    notification_id: str
    notification_type: str  # 'failure_alert' or 'recovery_confirmation'
    recipients: List[str]
    subject: str
    body_text: str
    body_html: Optional[str] = None
    created_time: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    next_retry_time: Optional[datetime] = None

    def should_retry(self) -> bool:
        """Check if message should be retried."""
        if self.retry_count >= self.max_retries:
            return False
        if self.next_retry_time is None:
            return True
        return datetime.now() >= self.next_retry_time

    def schedule_retry(self, delay_seconds: int) -> None:
        """Schedule next retry attempt."""
        self.retry_count += 1
        self.next_retry_time = datetime.now() + timedelta(seconds=delay_seconds)


class NotificationTemplate:
    """Template engine for generating notification content."""

    # Default templates
    FAILURE_ALERT_SUBJECT = "$subject_prefix Node Failure Alert - $node_id"
    FAILURE_ALERT_TEXT = """
KAFKA SELF-HEALING SYSTEM - FAILURE ALERT

=== NODE INFORMATION ===
$node_details

=== FAILURE DETAILS ===
Status: FAILED
Failure Time: $failure_time
Last Successful Check: $last_success_time
Error Message: $error_message

=== RECOVERY ATTEMPTS ($total_recovery_attempts total) ===
$recovery_history

=== CONFIGURATION ===
Monitoring Methods: $monitoring_methods
Recovery Actions: $recovery_actions
$log_excerpts

=== ACTION REQUIRED ===
This node has failed automated recovery and requires manual intervention.
Please investigate the error details and recovery attempt logs above.

---
Kafka Self-Healing System
Generated at: $generated_time
"""

    FAILURE_ALERT_HTML = """
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .header { background-color: #d32f2f; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .content { margin: 20px 0; }
        .section { background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #ddd; }
        .node-info { border-left-color: #2196f3; }
        .failure-details { border-left-color: #f44336; background-color: #ffebee; }
        .recovery-history { border-left-color: #ff9800; background-color: #fff3e0; }
        .configuration { border-left-color: #4caf50; background-color: #e8f5e8; }
        .log-excerpts { border-left-color: #9c27b0; background-color: #f3e5f5; }
        .action-required { border-left-color: #d32f2f; background-color: #ffcdd2; }
        .footer { color: #666; font-size: 12px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px; }
        .status-failed { color: #d32f2f; font-weight: bold; }
        .status-success { color: #4caf50; font-weight: bold; }
        .recovery-attempt { margin: 10px 0; padding: 10px; background-color: #fff; border-radius: 3px; border: 1px solid #ddd; }
        .recovery-attempt h4 { margin: 0 0 10px 0; color: #333; }
        pre.output { background-color: #f5f5f5; padding: 8px; border-radius: 3px; font-size: 12px; overflow-x: auto; }
        pre.error { background-color: #ffebee; padding: 8px; border-radius: 3px; font-size: 12px; overflow-x: auto; color: #d32f2f; }
        code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
        ul { margin: 10px 0; }
        li { margin: 5px 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 Kafka Self-Healing System - Failure Alert</h1>
        <p>Node <strong>$node_id</strong> requires immediate attention</p>
    </div>
    
    <div class="content">
        <div class="section node-info">
            <h3>📋 Node Information</h3>
            <p><strong>Node ID:</strong> $node_id</p>
            <p><strong>Type:</strong> $node_type</p>
            <p><strong>Host:</strong> $host:$port</p>
            <p><strong>JMX Port:</strong> $jmx_port</p>
            <p><strong>Status:</strong> <span class="status-failed">FAILED</span></p>
        </div>
        
        <div class="section failure-details">
            <h3>❌ Failure Details</h3>
            <p><strong>Failure Time:</strong> $failure_time</p>
            <p><strong>Last Successful Check:</strong> $last_success_time</p>
            <p><strong>Error Message:</strong></p>
            <pre class="error">$error_message</pre>
        </div>
        
        <div class="section recovery-history">
            <h3>🔄 Recovery Attempts ($total_recovery_attempts total)</h3>
            $recovery_history_html
        </div>
        
        <div class="section configuration">
            <h3>⚙️ Configuration</h3>
            <p><strong>Monitoring Methods:</strong> $monitoring_methods</p>
            <p><strong>Recovery Actions:</strong> $recovery_actions</p>
        </div>
        
        $log_excerpts_html
        
        <div class="section action-required">
            <h3>⚠️ Action Required</h3>
            <p><strong>This node has failed automated recovery and requires manual intervention.</strong></p>
            <p>Please investigate the error details and recovery attempt logs above. Common next steps:</p>
            <ul>
                <li>Check node system resources (CPU, memory, disk space)</li>
                <li>Verify network connectivity to the node</li>
                <li>Review application logs for additional error details</li>
                <li>Consider manual restart or configuration changes</li>
            </ul>
        </div>
    </div>
    
    <div class="footer">
        <p>🤖 Kafka Self-Healing System<br>
        Generated at: $generated_time</p>
    </div>
</body>
</html>
"""

    RECOVERY_CONFIRMATION_SUBJECT = "$subject_prefix Recovery Success - $node_id"
    RECOVERY_CONFIRMATION_TEXT = """
KAFKA SELF-HEALING SYSTEM - RECOVERY CONFIRMATION

=== NODE INFORMATION ===
Node ID: $node_id
Type: $node_type
Host: $host:$port
JMX Port: $jmx_port

=== RECOVERY DETAILS ===
Status: RECOVERED
Recovery Time: $recovery_time
Downtime Duration: $downtime_duration
Total Recovery Attempts: $total_attempts

=== SUCCESSFUL RECOVERY ACTION ===
$successful_action_details
$failed_attempts

=== STATUS ===
✅ The node is now healthy and back in service.
✅ Monitoring has resumed normal operation.
✅ No further action is required at this time.

---
Kafka Self-Healing System
Generated at: $generated_time
"""

    RECOVERY_CONFIRMATION_HTML = """
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .header { background-color: #388e3c; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .content { margin: 20px 0; }
        .section { background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #ddd; }
        .node-info { border-left-color: #2196f3; }
        .recovery-details { border-left-color: #4caf50; background-color: #e8f5e8; }
        .successful-action { border-left-color: #4caf50; background-color: #e8f5e8; }
        .failed-attempts { border-left-color: #ff9800; background-color: #fff3e0; }
        .status-summary { border-left-color: #4caf50; background-color: #e8f5e8; }
        .footer { color: #666; font-size: 12px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px; }
        .status-recovered { color: #4caf50; font-weight: bold; }
        .failed-attempt { margin: 10px 0; padding: 10px; background-color: #fff; border-radius: 3px; border: 1px solid #ddd; }
        pre.error { background-color: #ffebee; padding: 8px; border-radius: 3px; font-size: 12px; overflow-x: auto; color: #d32f2f; }
        code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
        .success-icon { color: #4caf50; font-size: 18px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>✅ Kafka Self-Healing System - Recovery Confirmation</h1>
        <p>Node <strong>$node_id</strong> has been successfully recovered</p>
    </div>
    
    <div class="content">
        <div class="section node-info">
            <h3>📋 Node Information</h3>
            <p><strong>Node ID:</strong> $node_id</p>
            <p><strong>Type:</strong> $node_type</p>
            <p><strong>Host:</strong> $host:$port</p>
            <p><strong>JMX Port:</strong> $jmx_port</p>
            <p><strong>Status:</strong> <span class="status-recovered">RECOVERED</span></p>
        </div>
        
        <div class="section recovery-details">
            <h3>🔄 Recovery Details</h3>
            <p><strong>Recovery Time:</strong> $recovery_time</p>
            <p><strong>Downtime Duration:</strong> $downtime_duration</p>
            <p><strong>Total Recovery Attempts:</strong> $total_attempts</p>
        </div>
        
        <div class="section successful-action">
            <h3>✅ Successful Recovery Action</h3>
            <p><strong>Action:</strong> $successful_action</p>
            <pre>$successful_action_details</pre>
        </div>
        
        $failed_attempts_html
        
        <div class="section status-summary">
            <h3>📊 Status Summary</h3>
            <p><span class="success-icon">✅</span> <strong>The node is now healthy and back in service.</strong></p>
            <p><span class="success-icon">✅</span> <strong>Monitoring has resumed normal operation.</strong></p>
            <p><span class="success-icon">✅</span> <strong>No further action is required at this time.</strong></p>
        </div>
    </div>
    
    <div class="footer">
        <p>🤖 Kafka Self-Healing System<br>
        Generated at: $generated_time</p>
    </div>
</body>
</html>
"""

    def __init__(self, custom_templates: Optional[Dict[str, str]] = None):
        """Initialize template engine with optional custom templates."""
        self.templates = {
            'failure_alert_subject': self.FAILURE_ALERT_SUBJECT,
            'failure_alert_text': self.FAILURE_ALERT_TEXT,
            'failure_alert_html': self.FAILURE_ALERT_HTML,
            'recovery_confirmation_subject': self.RECOVERY_CONFIRMATION_SUBJECT,
            'recovery_confirmation_text': self.RECOVERY_CONFIRMATION_TEXT,
            'recovery_confirmation_html': self.RECOVERY_CONFIRMATION_HTML,
        }
        
        if custom_templates:
            self.templates.update(custom_templates)

    def render_failure_alert(self, node: NodeConfig, recovery_history: List[RecoveryResult],
                           error_message: str, subject_prefix: str = "[Kafka Self-Healing]",
                           last_success_time: Optional[datetime] = None,
                           log_excerpts: Optional[List[str]] = None) -> Dict[str, str]:
        """Render failure alert notification content with detailed information."""
        # Format recovery history with detailed information
        recovery_text = []
        recovery_html = []
        
        if recovery_history:
            for i, result in enumerate(recovery_history, 1):
                status = "SUCCESS" if result.success else "FAILED"
                duration = "N/A"
                
                # Format execution details
                exec_details = [
                    f"{i}. Action: {result.action_type}",
                    f"   Command: {result.command_executed}",
                    f"   Time: {result.execution_time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"   Status: {status}",
                    f"   Exit Code: {result.exit_code}"
                ]
                
                # Add output if available
                if result.stdout:
                    stdout_preview = result.stdout[:300] + "..." if len(result.stdout) > 300 else result.stdout
                    exec_details.append(f"   Output: {stdout_preview}")
                
                if result.stderr:
                    stderr_preview = result.stderr[:300] + "..." if len(result.stderr) > 300 else result.stderr
                    exec_details.append(f"   Error: {stderr_preview}")
                
                recovery_text.extend(exec_details)
                recovery_text.append("")  # Empty line between attempts
                
                # HTML version with better formatting
                status_class = "success" if result.success else "failed"
                html_entry = f"""
                <div class="recovery-attempt">
                    <h4>Attempt {i}: {result.action_type}</h4>
                    <p><strong>Command:</strong> <code>{result.command_executed}</code></p>
                    <p><strong>Time:</strong> {result.execution_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Status:</strong> <span class="status-{status_class.lower()}">{status}</span></p>
                    <p><strong>Exit Code:</strong> {result.exit_code}</p>
                """
                
                if result.stdout:
                    stdout_preview = result.stdout[:300] + "..." if len(result.stdout) > 300 else result.stdout
                    html_entry += f"<p><strong>Output:</strong><br><pre class='output'>{stdout_preview}</pre></p>"
                
                if result.stderr:
                    stderr_preview = result.stderr[:300] + "..." if len(result.stderr) > 300 else result.stderr
                    html_entry += f"<p><strong>Error:</strong><br><pre class='error'>{stderr_preview}</pre></p>"
                
                html_entry += "</div>"
                recovery_html.append(html_entry)
        
        recovery_history_text = "\n".join(recovery_text) if recovery_text else "No recovery attempts made"
        recovery_history_html = "\n".join(recovery_html) if recovery_html else "<p>No recovery attempts made</p>"
        
        # Format log excerpts if provided
        log_excerpts_text = ""
        log_excerpts_html = ""
        if log_excerpts:
            log_excerpts_text = "\n\nRecent Log Excerpts:\n" + "\n".join(f"- {excerpt}" for excerpt in log_excerpts[-10:])
            log_excerpts_html = "<h3>Recent Log Excerpts</h3><ul>" + "".join(f"<li>{excerpt}</li>" for excerpt in log_excerpts[-10:]) + "</ul>"
        
        # Format node details
        node_details = [
            f"Node ID: {node.node_id}",
            f"Type: {node.node_type}",
            f"Host: {node.host}",
            f"Port: {node.port}"
        ]
        
        if node.jmx_port:
            node_details.append(f"JMX Port: {node.jmx_port}")
        
        if node.monitoring_methods:
            node_details.append(f"Monitoring Methods: {', '.join(node.monitoring_methods)}")
        
        if node.recovery_actions:
            node_details.append(f"Recovery Actions: {', '.join(node.recovery_actions)}")
        
        node_details_text = "\n".join(node_details)
        
        # Template variables
        variables = {
            'subject_prefix': subject_prefix,
            'node_id': node.node_id,
            'node_type': node.node_type,
            'host': node.host,
            'port': str(node.port),
            'jmx_port': str(node.jmx_port) if node.jmx_port else 'N/A',
            'node_details': node_details_text,
            'failure_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_success_time': last_success_time.strftime('%Y-%m-%d %H:%M:%S') if last_success_time else 'Unknown',
            'recovery_history': recovery_history_text,
            'recovery_history_html': recovery_history_html,
            'error_message': error_message,
            'log_excerpts': log_excerpts_text,
            'log_excerpts_html': log_excerpts_html,
            'generated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_recovery_attempts': str(len(recovery_history)),
            'monitoring_methods': ', '.join(node.monitoring_methods) if node.monitoring_methods else 'Default',
            'recovery_actions': ', '.join(node.recovery_actions) if node.recovery_actions else 'Default'
        }
        
        return {
            'subject': Template(self.templates['failure_alert_subject']).safe_substitute(variables),
            'text': Template(self.templates['failure_alert_text']).safe_substitute(variables),
            'html': Template(self.templates['failure_alert_html']).safe_substitute(variables)
        }

    def render_recovery_confirmation(self, node: NodeConfig, successful_action: RecoveryResult,
                                   downtime_duration: str, subject_prefix: str = "[Kafka Self-Healing]",
                                   failed_attempts: Optional[List[RecoveryResult]] = None) -> Dict[str, str]:
        """Render recovery confirmation notification content with detailed information."""
        # Format failed attempts if provided
        failed_attempts_text = ""
        failed_attempts_html = ""
        
        if failed_attempts:
            failed_text = []
            failed_html = []
            
            for i, result in enumerate(failed_attempts, 1):
                failed_text.append(f"{i}. {result.action_type} at {result.execution_time.strftime('%Y-%m-%d %H:%M:%S')} - FAILED")
                if result.stderr:
                    stderr_preview = result.stderr[:200] + "..." if len(result.stderr) > 200 else result.stderr
                    failed_text.append(f"   Error: {stderr_preview}")
                
                # HTML version
                html_entry = f"""
                <div class="failed-attempt">
                    <p><strong>Attempt {i}:</strong> {result.action_type}</p>
                    <p><strong>Time:</strong> {result.execution_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Command:</strong> <code>{result.command_executed}</code></p>
                """
                if result.stderr:
                    stderr_preview = result.stderr[:200] + "..." if len(result.stderr) > 200 else result.stderr
                    html_entry += f"<p><strong>Error:</strong><br><pre class='error'>{stderr_preview}</pre></p>"
                html_entry += "</div>"
                failed_html.append(html_entry)
            
            failed_attempts_text = "\n\nPrevious Failed Attempts:\n" + "\n".join(failed_text)
            failed_attempts_html = "<h3>Previous Failed Attempts</h3>" + "\n".join(failed_html)
        
        # Format successful action details
        successful_action_details = [
            f"Action Type: {successful_action.action_type}",
            f"Command: {successful_action.command_executed}",
            f"Execution Time: {successful_action.execution_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Exit Code: {successful_action.exit_code}"
        ]
        
        if successful_action.stdout:
            stdout_preview = successful_action.stdout[:300] + "..." if len(successful_action.stdout) > 300 else successful_action.stdout
            successful_action_details.append(f"Output: {stdout_preview}")
        
        successful_action_text = "\n".join(successful_action_details)
        
        # Template variables
        variables = {
            'subject_prefix': subject_prefix,
            'node_id': node.node_id,
            'node_type': node.node_type,
            'host': node.host,
            'port': str(node.port),
            'jmx_port': str(node.jmx_port) if node.jmx_port else 'N/A',
            'recovery_time': successful_action.execution_time.strftime('%Y-%m-%d %H:%M:%S'),
            'downtime_duration': downtime_duration,
            'successful_action': f"{successful_action.action_type}: {successful_action.command_executed}",
            'successful_action_details': successful_action_text,
            'failed_attempts': failed_attempts_text,
            'failed_attempts_html': failed_attempts_html,
            'total_attempts': str(len(failed_attempts) + 1 if failed_attempts else 1),
            'generated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return {
            'subject': Template(self.templates['recovery_confirmation_subject']).safe_substitute(variables),
            'text': Template(self.templates['recovery_confirmation_text']).safe_substitute(variables),
            'html': Template(self.templates['recovery_confirmation_html']).safe_substitute(variables)
        }


class DeliveryQueue:
    """Queue for managing notification delivery with retry logic."""

    def __init__(self, max_queue_size: int = 1000):
        """Initialize delivery queue."""
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.retry_queue = queue.Queue(maxsize=max_queue_size)
        self.running = False
        self.worker_thread = None
        self.retry_thread = None
        self.logger = logging.getLogger(__name__)

    def start(self) -> None:
        """Start the delivery queue worker threads."""
        if self.running:
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self.worker_thread.start()
        self.retry_thread.start()
        self.logger.info("Delivery queue started")

    def stop(self) -> None:
        """Stop the delivery queue worker threads."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        if self.retry_thread:
            self.retry_thread.join(timeout=5)
        self.logger.info("Delivery queue stopped")

    def enqueue(self, message: NotificationMessage) -> bool:
        """Add a message to the delivery queue."""
        try:
            self.queue.put_nowait(message)
            self.logger.debug(f"Enqueued notification {message.notification_id}")
            return True
        except queue.Full:
            self.logger.error(f"Delivery queue full, dropping notification {message.notification_id}")
            return False

    def enqueue_retry(self, message: NotificationMessage) -> bool:
        """Add a message to the retry queue."""
        try:
            self.retry_queue.put_nowait(message)
            self.logger.debug(f"Enqueued retry for notification {message.notification_id}")
            return True
        except queue.Full:
            self.logger.error(f"Retry queue full, dropping notification {message.notification_id}")
            return False

    def _worker_loop(self) -> None:
        """Main worker loop for processing delivery queue."""
        while self.running:
            try:
                message = self.queue.get(timeout=1)
                self._process_message(message)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in delivery worker: {e}")

    def _retry_loop(self) -> None:
        """Worker loop for processing retry queue."""
        while self.running:
            try:
                message = self.retry_queue.get(timeout=1)
                if message.should_retry():
                    self._process_message(message)
                else:
                    self.logger.warning(f"Max retries exceeded for notification {message.notification_id}")
                self.retry_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in retry worker: {e}")

    def _process_message(self, message: NotificationMessage) -> None:
        """Process a single notification message."""
        # This method will be overridden by NotificationService
        self.logger.debug(f"Processing notification {message.notification_id}")

    def get_queue_sizes(self) -> Dict[str, int]:
        """Get current queue sizes for monitoring."""
        return {
            'delivery_queue': self.queue.qsize(),
            'retry_queue': self.retry_queue.qsize()
        }


class NotificationService:
    """Main notification service orchestrator."""

    def __init__(self, config: NotificationConfig, template_engine: Optional[NotificationTemplate] = None):
        """Initialize notification service."""
        self.config = config
        self.template_engine = template_engine or NotificationTemplate()
        self.delivery_queue = DeliveryQueue()
        self.notifiers: Dict[str, 'Notifier'] = {}
        self.delivery_callbacks: List[Callable[[NotificationResult], None]] = []
        self.logger = logging.getLogger(__name__)
        self._notification_counter = 0
        self._counter_lock = threading.Lock()
        
        # Delivery tracking
        self._delivery_stats = {
            'total_sent': 0,
            'total_delivered': 0,
            'total_failed': 0,
            'total_retries': 0,
            'notifier_stats': {}
        }
        self._stats_lock = threading.Lock()
        
        # Override delivery queue's message processing
        self.delivery_queue._process_message = self._process_delivery_message

    def start(self) -> None:
        """Start the notification service."""
        self.delivery_queue.start()
        self.logger.info("Notification service started")

    def stop(self) -> None:
        """Stop the notification service."""
        self.delivery_queue.stop()
        self.logger.info("Notification service stopped")

    def register_notifier(self, notifier_type: str, notifier: 'Notifier') -> None:
        """Register a notification delivery mechanism."""
        self.notifiers[notifier_type] = notifier
        self.logger.info(f"Registered notifier: {notifier_type}")

    def register_delivery_callback(self, callback: Callable[[NotificationResult], None]) -> None:
        """Register a callback for delivery results."""
        self.delivery_callbacks.append(callback)

    def send_failure_alert(self, node: NodeConfig, recovery_history: List[RecoveryResult],
                          error_message: str, last_success_time: Optional[datetime] = None,
                          log_excerpts: Optional[List[str]] = None) -> str:
        """Send failure alert notification."""
        notification_id = self._generate_notification_id()
        
        # Render notification content
        content = self.template_engine.render_failure_alert(
            node, recovery_history, error_message, self.config.subject_prefix,
            last_success_time, log_excerpts
        )
        
        # Create notification message
        message = NotificationMessage(
            notification_id=notification_id,
            notification_type='failure_alert',
            recipients=self.config.recipients,
            subject=content['subject'],
            body_text=content['text'],
            body_html=content['html']
        )
        
        # Enqueue for delivery
        if self.delivery_queue.enqueue(message):
            with self._stats_lock:
                self._delivery_stats['total_sent'] += 1
            self.logger.info(f"Failure alert queued for node {node.node_id}: {notification_id}")
        else:
            self.logger.error(f"Failed to queue failure alert for node {node.node_id}")
        
        return notification_id

    def send_recovery_confirmation(self, node: NodeConfig, successful_action: RecoveryResult,
                                 downtime_duration: str, failed_attempts: Optional[List[RecoveryResult]] = None) -> str:
        """Send recovery confirmation notification."""
        notification_id = self._generate_notification_id()
        
        # Render notification content
        content = self.template_engine.render_recovery_confirmation(
            node, successful_action, downtime_duration, self.config.subject_prefix, failed_attempts
        )
        
        # Create notification message
        message = NotificationMessage(
            notification_id=notification_id,
            notification_type='recovery_confirmation',
            recipients=self.config.recipients,
            subject=content['subject'],
            body_text=content['text'],
            body_html=content['html']
        )
        
        # Enqueue for delivery
        if self.delivery_queue.enqueue(message):
            with self._stats_lock:
                self._delivery_stats['total_sent'] += 1
            self.logger.info(f"Recovery confirmation queued for node {node.node_id}: {notification_id}")
        else:
            self.logger.error(f"Failed to queue recovery confirmation for node {node.node_id}")
        
        return notification_id

    def get_status(self) -> Dict[str, Any]:
        """Get notification service status."""
        return {
            'running': self.delivery_queue.running,
            'queue_sizes': self.delivery_queue.get_queue_sizes(),
            'registered_notifiers': list(self.notifiers.keys()),
            'config': {
                'smtp_host': self.config.smtp_host,
                'smtp_port': self.config.smtp_port,
                'sender_email': self.config.sender_email,
                'recipient_count': len(self.config.recipients)
            }
        }

    def _generate_notification_id(self) -> str:
        """Generate unique notification ID."""
        with self._counter_lock:
            self._notification_counter += 1
            return f"notif_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._notification_counter:04d}"

    def _process_delivery_message(self, message: NotificationMessage) -> None:
        """Process a notification message from the delivery queue."""
        self.logger.debug(f"Processing notification {message.notification_id} (attempt {message.retry_count + 1})")
        
        # Track delivery attempts
        delivery_successful = False
        all_results = []
        
        # If no notifiers are registered, log error and fail
        if not self.notifiers:
            self.logger.error(f"No notifiers registered for notification {message.notification_id}")
            # Create immediate failure result
            error_result = NotificationResult(
                notification_id=message.notification_id,
                recipient="unknown",
                delivery_time=datetime.now(),
                success=False,
                error_message="No notifiers available",
                retry_count=message.retry_count
            )
            all_results.append(error_result)
            self._notify_delivery_result(error_result)
            self._handle_delivery_failure(message, "No notifiers available")
            return
        
        # Try each registered notifier
        for notifier_type, notifier in self.notifiers.items():
            try:
                self.logger.debug(f"Attempting delivery via {notifier_type} for notification {message.notification_id}")
                
                # Test connection before attempting delivery
                if not notifier.test_connection():
                    self.logger.warning(f"Connection test failed for {notifier_type}, skipping")
                    continue
                
                if isinstance(notifier, EmailNotifier):
                    # EmailNotifier returns a list of results
                    results = notifier.send(message)
                    all_results.extend(results)
                    
                    # Check if at least one recipient succeeded
                    successful_deliveries = [r for r in results if r.success]
                    if successful_deliveries:
                        delivery_successful = True
                        self.logger.info(f"Successfully delivered notification {message.notification_id} to {len(successful_deliveries)} recipients via {notifier_type}")
                    
                    # Notify callbacks for all results
                    for result in results:
                        self._notify_delivery_result(result)
                else:
                    # Other notifiers return a single result
                    result = notifier.send(message)
                    all_results.append(result)
                    self._notify_delivery_result(result)
                    
                    if result.success:
                        delivery_successful = True
                        self.logger.info(f"Successfully delivered notification {message.notification_id} via {notifier_type}")
                
                # If any notifier succeeded, we're done
                if delivery_successful:
                    break
                    
            except Exception as e:
                error_msg = f"Error in notifier {notifier_type}: {str(e)}"
                self.logger.error(error_msg)
                
                # Create error result for tracking
                error_result = NotificationResult(
                    notification_id=message.notification_id,
                    recipient="unknown",
                    delivery_time=datetime.now(),
                    success=False,
                    error_message=error_msg,
                    retry_count=message.retry_count
                )
                all_results.append(error_result)
                self._notify_delivery_result(error_result)
        
        # Handle delivery outcome
        if delivery_successful:
            self.logger.info(f"Notification {message.notification_id} delivered successfully after {message.retry_count + 1} attempts")
        else:
            self._handle_delivery_failure(message, f"All notifiers failed. Results: {[r.error_message for r in all_results if not r.success]}")

    def _handle_delivery_failure(self, message: NotificationMessage, error_summary: str) -> None:
        """Handle failed notification delivery."""
        if message.should_retry():
            # Calculate retry delay with exponential backoff and jitter
            # Use shorter delays for testing, longer for production
            base_delay = getattr(self, '_test_mode_delay', 30)  # Allow override for testing
            max_delay = getattr(self, '_test_mode_max_delay', 300)
            
            # Exponential backoff
            delay = min(base_delay * (2 ** message.retry_count), max_delay)
            
            # Add jitter to prevent thundering herd (±25% randomization)
            import random
            jitter = random.uniform(0.75, 1.25)
            delay = int(delay * jitter)
            
            message.schedule_retry(delay)
            
            self.logger.warning(f"Scheduling retry {message.retry_count + 1}/{message.max_retries} for notification {message.notification_id} in {delay} seconds. Error: {error_summary}")
            
            if not self.delivery_queue.enqueue_retry(message):
                self.logger.error(f"Failed to enqueue retry for notification {message.notification_id} - retry queue full")
        else:
            self.logger.error(f"Max retries ({message.max_retries}) exceeded for notification {message.notification_id}. Final error: {error_summary}")
            
            # Create final failure result
            final_result = NotificationResult(
                notification_id=message.notification_id,
                recipient="all",
                delivery_time=datetime.now(),
                success=False,
                error_message=f"Max retries exceeded: {error_summary}",
                retry_count=message.retry_count
            )
            self._notify_delivery_result(final_result)

    def set_test_mode(self, enabled: bool = True, base_delay: int = 1, max_delay: int = 5) -> None:
        """Enable test mode with shorter retry delays."""
        if enabled:
            self._test_mode_delay = base_delay
            self._test_mode_max_delay = max_delay
        else:
            if hasattr(self, '_test_mode_delay'):
                delattr(self, '_test_mode_delay')
            if hasattr(self, '_test_mode_max_delay'):
                delattr(self, '_test_mode_max_delay')

    def _notify_delivery_result(self, result: NotificationResult) -> None:
        """Notify registered callbacks of delivery results and update statistics."""
        # Update delivery statistics
        with self._stats_lock:
            if result.success:
                self._delivery_stats['total_delivered'] += 1
            else:
                self._delivery_stats['total_failed'] += 1
            
            if result.retry_count > 0:
                self._delivery_stats['total_retries'] += 1
        
        # Notify callbacks
        for callback in self.delivery_callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Error in delivery callback: {e}")

    def get_delivery_statistics(self) -> Dict[str, Any]:
        """Get delivery statistics for monitoring."""
        with self._stats_lock:
            stats = self._delivery_stats.copy()
        
        # Add queue statistics
        queue_stats = self.delivery_queue.get_queue_sizes()
        stats.update(queue_stats)
        
        # Calculate success rate
        total_attempts = stats['total_delivered'] + stats['total_failed']
        if total_attempts > 0:
            stats['success_rate'] = stats['total_delivered'] / total_attempts
        else:
            stats['success_rate'] = 0.0
        
        return stats

    def reset_delivery_statistics(self) -> None:
        """Reset delivery statistics."""
        with self._stats_lock:
            self._delivery_stats = {
                'total_sent': 0,
                'total_delivered': 0,
                'total_failed': 0,
                'total_retries': 0,
                'notifier_stats': {}
            }
        self.logger.info("Delivery statistics reset")

    def test_all_notifiers(self) -> Dict[str, bool]:
        """Test connection to all registered notifiers."""
        results = {}
        for notifier_type, notifier in self.notifiers.items():
            try:
                results[notifier_type] = notifier.test_connection()
                self.logger.info(f"Connection test for {notifier_type}: {'PASS' if results[notifier_type] else 'FAIL'}")
            except Exception as e:
                results[notifier_type] = False
                self.logger.error(f"Connection test for {notifier_type} failed with exception: {e}")
        
        return results

    def send_test_notifications(self, test_recipients: Optional[List[str]] = None) -> Dict[str, bool]:
        """Send test notifications through all notifiers."""
        results = {}
        test_message = NotificationMessage(
            notification_id=self._generate_notification_id(),
            notification_type="test",
            recipients=test_recipients or self.config.recipients[:1],  # Use first recipient if none specified
            subject=f"{self.config.subject_prefix} Test Notification",
            body_text="This is a test notification from the Kafka Self-Healing System.\n\nIf you receive this message, notifications are working correctly.",
            body_html="""
            <html>
            <body>
                <h2>Test Notification</h2>
                <p>This is a test notification from the Kafka Self-Healing System.</p>
                <p>If you receive this message, notifications are working correctly.</p>
                <p><strong>Timestamp:</strong> """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
            </body>
            </html>
            """
        )
        
        for notifier_type, notifier in self.notifiers.items():
            try:
                if isinstance(notifier, EmailNotifier):
                    delivery_results = notifier.send(test_message)
                    results[notifier_type] = any(r.success for r in delivery_results)
                else:
                    result = notifier.send(test_message)
                    results[notifier_type] = result.success
                
                self.logger.info(f"Test notification via {notifier_type}: {'SUCCESS' if results[notifier_type] else 'FAILED'}")
            except Exception as e:
                results[notifier_type] = False
                self.logger.error(f"Test notification via {notifier_type} failed with exception: {e}")
        
        return results


class Notifier(ABC):
    """Abstract base class for notification delivery mechanisms."""

    @abstractmethod
    def send(self, message: NotificationMessage) -> Union[NotificationResult, List[NotificationResult]]:
        """Send a notification message."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the notifier can connect to its delivery mechanism."""
        pass


class EmailNotifier(Notifier):
    """Email notification delivery using SMTP."""

    def __init__(self, config: NotificationConfig):
        """Initialize email notifier with SMTP configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)

    def send(self, message: NotificationMessage) -> List[NotificationResult]:
        """Send email notification to all recipients."""
        results = []
        
        for recipient in message.recipients:
            result = self._send_to_recipient(message, recipient)
            results.append(result)
        
        return results

    def _send_to_recipient(self, message: NotificationMessage, recipient: str) -> NotificationResult:
        """Send email to a single recipient."""
        try:
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = self.config.sender_email
            msg['To'] = recipient
            msg['Date'] = formatdate(localtime=True)
            
            # Add text part
            text_part = MIMEText(message.body_text, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Add HTML part if available
            if message.body_html:
                html_part = MIMEText(message.body_html, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Send email
            with self._create_smtp_connection() as smtp:
                smtp.send_message(msg)
            
            self.logger.info(f"Email sent successfully to {recipient} for notification {message.notification_id}")
            
            return NotificationResult(
                notification_id=message.notification_id,
                recipient=recipient,
                delivery_time=datetime.now(),
                success=True,
                retry_count=message.retry_count
            )
            
        except Exception as e:
            error_msg = f"Failed to send email to {recipient}: {str(e)}"
            self.logger.error(error_msg)
            
            return NotificationResult(
                notification_id=message.notification_id,
                recipient=recipient,
                delivery_time=datetime.now(),
                success=False,
                error_message=error_msg,
                retry_count=message.retry_count
            )

    def _create_smtp_connection(self) -> smtplib.SMTP:
        """Create and configure SMTP connection."""
        if self.config.use_ssl:
            # Use SSL connection
            context = ssl.create_default_context()
            smtp = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, context=context)
        else:
            # Use regular connection, potentially with STARTTLS
            smtp = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
            
            if self.config.use_tls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
        
        # Authenticate if credentials provided
        if self.config.smtp_username and self.config.smtp_password:
            smtp.login(self.config.smtp_username, self.config.smtp_password)
        
        return smtp

    def test_connection(self) -> bool:
        """Test SMTP connection and authentication."""
        try:
            with self._create_smtp_connection() as smtp:
                # Test connection by sending NOOP command
                smtp.noop()
            
            self.logger.info("SMTP connection test successful")
            return True
            
        except Exception as e:
            self.logger.error(f"SMTP connection test failed: {str(e)}")
            return False

    def send_test_email(self, test_recipient: Optional[str] = None) -> bool:
        """Send a test email to verify configuration."""
        recipient = test_recipient or (self.config.recipients[0] if self.config.recipients else None)
        
        if not recipient:
            self.logger.error("No recipient specified for test email")
            return False
        
        test_message = NotificationMessage(
            notification_id="test_email",
            notification_type="test",
            recipients=[recipient],
            subject=f"{self.config.subject_prefix} Test Email",
            body_text="This is a test email from the Kafka Self-Healing System.\n\nIf you receive this message, email notifications are configured correctly.",
            body_html="""
            <html>
            <body>
                <h2>Test Email</h2>
                <p>This is a test email from the Kafka Self-Healing System.</p>
                <p>If you receive this message, email notifications are configured correctly.</p>
            </body>
            </html>
            """
        )
        
        result = self._send_to_recipient(test_message, recipient)
        return result.success