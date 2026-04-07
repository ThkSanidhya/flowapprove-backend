import os
import uuid
from .utils import send_email_notification
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.db import models  # ADD THIS IMPORT for Q objects
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .models import *
from .serializers import *
from datetime import datetime

User = get_user_model()

# ==================== AUTH ====================

@api_view(['POST'])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    
    data = serializer.validated_data
    if User.objects.filter(email=data['email']).exists():
        return Response({'error': 'User already exists'}, status=400)
    
    with transaction.atomic():
        org = Organization.objects.create(name=data['organization_name'])
        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=data['password'],
            name=data['name'],
            role='ADMIN',
            organization=org
        )
    
    refresh = RefreshToken.for_user(user)
    return Response({
        'token': str(refresh.access_token),
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'organizationId': org.id,
            'organizationName': org.name
        }
    })

@api_view(['POST'])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    
    user = User.objects.filter(email=serializer.data['email']).first()
    if not user or not user.check_password(serializer.data['password']):
        return Response({'error': 'Invalid credentials'}, status=401)
    
    refresh = RefreshToken.for_user(user)
    return Response({
        'token': str(refresh.access_token),
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'organizationId': user.organization.id if user.organization else None,
            'organizationName': user.organization.name if user.organization else None
        }
    })

# ==================== USER MANAGEMENT ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def users(request):
    if request.user.role != 'ADMIN':
        return Response({'error': 'Admin access required'}, status=403)
    
    if request.method == 'GET':
        users = User.objects.filter(organization=request.user.organization)
        return Response(UserSerializer(users, many=True).data)
    
    # POST - Create new user
    data = request.data
    if User.objects.filter(email=data['email']).exists():
        return Response({'error': 'User already exists'}, status=400)
    
    user = User.objects.create_user(
        username=data['email'],
        email=data['email'],
        password=data['password'],
        name=data['name'],
        role=data.get('role', 'USER'),
        organization=request.user.organization
    )
    return Response(UserSerializer(user).data, status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_detail(request, id):
    if request.user.role != 'ADMIN':
        return Response({'error': 'Admin access required'}, status=403)
    
    try:
        user = User.objects.get(id=id, organization=request.user.organization)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    
    if request.method == 'PUT':
        data = request.data
        user.name = data.get('name', user.name)
        user.email = data.get('email', user.email)
        user.role = data.get('role', user.role)
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        user.save()
        return Response(UserSerializer(user).data)
    
    # DELETE
    if user.id == request.user.id:
        return Response({'error': 'Cannot delete yourself'}, status=400)
    user.delete()
    return Response({'message': 'User deleted'}, status=204)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    return Response({
        'id': request.user.id,
        'name': request.user.name,
        'email': request.user.email,
        'role': request.user.role,
        'organizationId': request.user.organization.id if request.user.organization else None,
        'organizationName': request.user.organization.name if request.user.organization else None
    })

# ==================== WORKFLOWS ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def workflows(request):
    if request.method == 'GET':
        workflows = Workflow.objects.filter(organization=request.user.organization)
        return Response(WorkflowSerializer(workflows, many=True).data)
    
    # POST - Create workflow
    data = request.data
    workflow = Workflow.objects.create(
        name=data['name'],
        organization=request.user.organization
    )
    for i, step in enumerate(data.get('steps', [])):
        WorkflowStep.objects.create(
            workflow=workflow,
            order=i + 1,
            user_id=step['userId']
        )
    return Response(WorkflowSerializer(workflow).data, status=201)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def workflow_detail(request, id):
    if request.user.role != 'ADMIN':
        return Response({'error': 'Admin access required'}, status=403)
    
    try:
        workflow = Workflow.objects.get(id=id, organization=request.user.organization)
    except Workflow.DoesNotExist:
        return Response({'error': 'Workflow not found'}, status=404)
    
    if request.method == 'GET':
        return Response(WorkflowSerializer(workflow).data)
    
    elif request.method == 'PUT':
        data = request.data
        workflow.name = data.get('name', workflow.name)
        workflow.save()
        workflow.steps.all().delete()
        for i, step in enumerate(data.get('steps', [])):
            WorkflowStep.objects.create(
                workflow=workflow,
                order=i + 1,
                user_id=step['userId']
            )
        return Response(WorkflowSerializer(workflow).data)
    
    elif request.method == 'DELETE':
        workflow.delete()
        return Response({'message': 'Workflow deleted'}, status=204)

# ==================== DOCUMENTS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_document(request):
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file uploaded'}, status=400)
    
    title = request.POST.get('title', file.name)
    description = request.POST.get('description', '')
    workflow_id = request.POST.get('workflowId')
    
    # Save file
    ext = os.path.splitext(file.name)[1]
    file_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join('documents', file_name)
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'wb+') as dest:
        for chunk in file.chunks():
            dest.write(chunk)
    
    file_size = os.path.getsize(full_path)
    
    with transaction.atomic():
        doc = Document.objects.create(
            title=title,
            description=description,
            file=file_path,
            file_name=file.name,
            file_url = f"/media/{file_path}",
            file_type=file.content_type,
            file_size=file_size,
            organization=request.user.organization,
            created_by=request.user,
            workflow_id=workflow_id,
            status='PENDING',
            current_step=1
        )
        
        # Create approvals
        if workflow_id:
            workflow = Workflow.objects.get(id=workflow_id)
            for step in workflow.steps.all():
                DocumentApproval.objects.create(
                    document=doc,
                    step_order=step.order,
                    user=step.user,
                    status='PENDING'
                )
        
        DocumentHistory.objects.create(
            document=doc,
            user=request.user,
            action='UPLOADED',
            comment=f'Document "{doc.title}" uploaded'
        )
    
    return Response(DocumentSerializer(doc).data, status=201)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_documents(request):
    if request.user.role == 'ADMIN':
        docs = Document.objects.filter(organization=request.user.organization)
    else:
        docs = Document.objects.filter(
            organization=request.user.organization
        ).filter(
            models.Q(created_by=request.user) | 
            models.Q(approvals__user=request.user)
        ).distinct()
    return Response(DocumentSerializer(docs, many=True).data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_document_detail(request, id):
    try:
        doc = Document.objects.get(id=id, organization=request.user.organization)
    except Document.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)
    
    # Get approvals
    approvals = doc.approvals.all().order_by('step_order')
    
    # Build timeline
    timeline = []
    if doc.workflow:
        for step in doc.workflow.steps.all().order_by('order'):
            approval = approvals.filter(step_order=step.order).first()
            timeline.append({
                'stepOrder': step.order,
                'user': {'id': step.user.id, 'name': step.user.name, 'email': step.user.email},
                'status': approval.status if approval else 'PENDING',
                'comment': approval.comment if approval else None,
                'approvedAt': approval.approved_at if approval else None,
                'isCompleted': approval.status == 'APPROVED' if approval else False,
                'isCurrent': step.order == doc.current_step and doc.status == 'PENDING'
            })
    
    current_approval = approvals.filter(step_order=doc.current_step).first()
    can_approve = (
        doc.status == 'PENDING' and 
        current_approval and 
        current_approval.user_id == request.user.id and
        current_approval.status == 'PENDING'
    )
    
    total_steps = doc.workflow.steps.count() if doc.workflow else 1
    completed_steps = approvals.filter(status='APPROVED').count()
    progress = round((completed_steps / total_steps) * 100) if total_steps > 0 else 0
    
    response_data = DocumentSerializer(doc).data
    response_data['canApprove'] = can_approve
    response_data['currentStep'] = doc.current_step
    response_data['timeline'] = timeline
    response_data['progress'] = progress
    response_data['comments'] = [
        {'id': c.id, 'user': {'id': c.user.id, 'name': c.user.name}, 'comment': c.comment, 'pageNumber': c.page_number, 'createdAt': c.created_at}
        for c in doc.comments.all().order_by('-created_at')
    ]
    response_data['history'] = [
        {'id': h.id, 'user': {'id': h.user.id, 'name': h.user.name}, 'action': h.action, 'comment': h.comment, 'createdAt': h.created_at}
        for h in doc.history.all().order_by('-created_at')
    ]
    response_data['versions'] = [
        {'id': v.id, 'versionNumber': v.version_number, 'fileName': v.file_name, 'fileUrl': v.file_url, 'fileSize': v.file_size, 'uploadedBy': {'name': v.uploaded_by.name}, 'versionNote': v.version_note, 'createdAt': v.created_at}
        for v in doc.versions.all().order_by('-version_number')
    ]
    
    return Response(response_data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_document(request, id):
    try:
        doc = Document.objects.get(id=id)
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=404)
    
    current_approval = doc.approvals.filter(step_order=doc.current_step, user=request.user).first()
    if not current_approval:
        return Response({'error': 'You are not authorized to approve this document'}, status=403)
    
    if current_approval.status != 'PENDING':
        return Response({'error': 'This step has already been processed'}, status=400)
    
    current_approval.status = 'APPROVED'
    current_approval.comment = request.data.get('comment', '')
    current_approval.approved_at = datetime.now()
    current_approval.save()
    
    total_steps = doc.workflow.steps.count() if doc.workflow else 1
    if doc.current_step < total_steps:
        doc.current_step += 1
        doc.save()
    else:
        doc.status = 'APPROVED'
        doc.save()
    
    DocumentHistory.objects.create(
        document=doc,
        user=request.user,
        action='APPROVED',
        comment=request.data.get('comment', '')
    )
    
    return Response({'message': 'Document approved successfully', 'current_step': doc.current_step})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_document(request, id):
    try:
        doc = Document.objects.get(id=id)
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=404)
    
    doc.status = 'REJECTED'
    doc.save()
    
    DocumentHistory.objects.create(
        document=doc,
        user=request.user,
        action='REJECTED',
        comment=request.data.get('comment', '')
    )
    
    return Response({'message': 'Rejected'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_back_document(request, id):
    try:
        doc = Document.objects.get(id=id)
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=404)
    
    # Find current approval
    current_approval = doc.approvals.filter(step_order=doc.current_step).first()
    if not current_approval:
        return Response({'error': f'No approval found for step {doc.current_step}'}, status=400)
    
    if current_approval.user.id != request.user.id:
        return Response({'error': f'You are not authorized. This step is assigned to {current_approval.user.name}'}, status=403)
    
    if current_approval.status != 'PENDING':
        return Response({'error': 'This step has already been processed'}, status=400)
    
    reason = request.data.get('reason')
    if not reason:
        return Response({'error': 'Reason required'}, status=400)
    
    # Mark current as rejected
    current_approval.status = 'REJECTED'
    current_approval.comment = reason
    current_approval.save()
    
    # Move back one step
    prev_step = max(1, doc.current_step - 1)
    doc.current_step = prev_step
    doc.status = 'PENDING'
    doc.save()
    
    # Reset previous approval to pending (if exists and was approved)
    prev_approval = doc.approvals.filter(step_order=prev_step).first()
    if prev_approval and prev_approval.status == 'APPROVED':
        prev_approval.status = 'PENDING'
        prev_approval.approved_at = None
        # Use empty string instead of None to avoid IntegrityError
        prev_approval.comment = ''
        prev_approval.save()
    
    DocumentHistory.objects.create(
        document=doc,
        user=request.user,
        action='SENT_BACK',
        comment=f'Sent back to step {prev_step}: {reason}'
    )
    
    return Response({'message': f'Sent back to step {prev_step}'})

# ==================== DASHBOARD ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    docs = Document.objects.filter(organization=request.user.organization)
    if request.user.role != 'ADMIN':
        docs = docs.filter(
            models.Q(created_by=request.user) |
            models.Q(approvals__user=request.user)
        ).distinct()
    
    pending_my_action = 0
    for doc in docs:
        approval = doc.approvals.filter(step_order=doc.current_step, user=request.user).first()
        if doc.status == 'PENDING' and approval and approval.status == 'PENDING':
            pending_my_action += 1
    
    return Response({
        'totalDocuments': docs.count(),
        'inProgress': docs.filter(status='PENDING').count(),
        'pendingMyAction': pending_my_action,
        'approvedByMe': docs.filter(approvals__user=request.user, approvals__status='APPROVED').count(),
        'sentBack': docs.filter(status='REJECTED').count(),
        'completed': docs.filter(status='APPROVED').count(),
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_documents(request):
    user = request.user
    org = user.organization
    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 10))
    status = request.GET.get('status', '')
    search = request.GET.get('search', '')
    
    if user.role == 'ADMIN':
        docs = Document.objects.filter(organization=org)
    else:
        docs = Document.objects.filter(
            organization=org
        ).filter(
            models.Q(created_by=user) | 
            models.Q(approvals__user=user)
        ).distinct()
    
    if status:
        docs = docs.filter(status=status)
    if search:
        docs = docs.filter(
            models.Q(title__icontains=search) |
            models.Q(id__icontains=search)
        )
    
    total = docs.count()
    start = (page - 1) * limit
    docs = docs.order_by('-created_at')[start:start+limit]
    
    result = []
    for doc in docs:
        current_approval = doc.approvals.filter(step_order=doc.current_step).first()
        can_approve = (
            doc.status == 'PENDING' and 
            current_approval and 
            current_approval.user_id == user.id and
            current_approval.status == 'PENDING'
        )
        result.append({
            'id': doc.id,
            'documentId': f"WF{str(doc.id).zfill(6)}",
            'title': doc.title,
            'description': doc.description,
            'uploadedBy': doc.created_by.name,
            'createdAt': doc.created_at,
            'updatedAt': doc.updated_at,
            'status': doc.status,
            'statusColor': '#28a745' if doc.status == 'APPROVED' else '#dc3545' if doc.status == 'REJECTED' else '#ffc107',
            'currentStep': doc.current_step,
            'totalSteps': doc.workflow.steps.count() if doc.workflow else 1,
            'currentOwner': current_approval.user.name if current_approval else 'No assignee',
            'isMyTurn': can_approve,
            'workflowName': doc.workflow.name if doc.workflow else None,
            'progress': round(((doc.current_step - 1) / max(doc.workflow.steps.count(), 1)) * 100) if doc.workflow else 0
        })
    
    return Response({
        'documents': result,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'totalPages': (total + limit - 1) // limit
        }
    })