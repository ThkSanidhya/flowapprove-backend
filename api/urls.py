from django.urls import path
from . import views

urlpatterns = [
    # Auth routes
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('auth/me/', views.get_current_user, name='get_current_user'),
    
    # User management routes
    path('users/', views.users, name='users'),
    path('users/<int:id>/', views.user_detail, name='user_detail'),
    
    # Workflow routes
    path('workflows/', views.workflows, name='workflows'),
    path('workflows/<int:id>/', views.workflow_detail, name='workflow_detail'),
    
    # Document routes
    path('documents/upload/', views.upload_document, name='upload_document'),
    path('documents/', views.get_documents, name='get_documents'),
    path('documents/<int:id>/', views.get_document_detail, name='get_document_detail'),
    path('documents/<int:id>/approve/', views.approve_document, name='approve_document'),
    path('documents/<int:id>/reject/', views.reject_document, name='reject_document'),
    path('documents/<int:id>/sendback/', views.send_back_document, name='send_back_document'),
    path('documents/<int:id>/upload-version/', views.upload_version, name='upload_version'),
    path('documents/<int:id>/recall/', views.recall_document, name='recall_document'),
    path('documents/<int:id>/reassign/', views.admin_reassign_step, name='admin_reassign_step'),
    path('documents/<int:id>/comments/', views.document_comments, name='document_comments'),
    path('documents/<int:id>/comments/reference/', views.document_comments, name='document_comments_reference'),
    
    # Dashboard routes
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
    path('dashboard/documents/', views.get_user_documents, name='get_user_documents'),
]