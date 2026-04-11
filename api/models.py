from django.db import models
from django.contrib.auth.models import AbstractUser

class Organization(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

class User(AbstractUser):
    ROLE_CHOICES = [('ADMIN', 'Admin'), ('USER', 'User')]
    
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='USER')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    def __str__(self):
        return self.email

class Workflow(models.Model):
    SENDBACK_CHOICES = [
        ('PREVIOUS_ONLY', 'Previous Step Only'),
        ('ANY_PREVIOUS', 'Any Previous Step'),
    ]

    name = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    sendback_type = models.CharField(
        max_length=15, choices=SENDBACK_CHOICES, default='PREVIOUS_ONLY'
    )
    created_at = models.DateTimeField(auto_now_add=True)

class WorkflowStep(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='steps')
    order = models.IntegerField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        ordering = ['order']

class Document(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='documents/')
    file_name = models.CharField(max_length=255)
    file_url = models.CharField(max_length=500)
    file_type = models.CharField(max_length=100)
    file_size = models.IntegerField()

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    current_step = models.IntegerField(default=1)

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    workflow = models.ForeignKey(Workflow, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'created_by']),
            models.Index(fields=['organization', '-created_at']),
        ]

class DocumentApproval(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='approvals')
    step_order = models.IntegerField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=Document.STATUS_CHOICES, default='PENDING')
    comment = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['document', 'step_order']),
            models.Index(fields=['user', 'status']),
        ]
        unique_together = [('document', 'step_order')]

class DocumentComment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField()
    page_number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class DocumentHistory(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    file = models.FileField(upload_to='versions/')
    file_name = models.CharField(max_length=255)
    file_url = models.CharField(max_length=500)
    file_type = models.CharField(max_length=100, default='application/pdf')
    file_size = models.IntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    version_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)