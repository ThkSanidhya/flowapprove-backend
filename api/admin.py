from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Organization, Workflow, Document

class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'name', 'role', 'organization')
    list_filter = ('role', 'organization')
    search_fields = ('email', 'name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'username')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Organization', {'fields': ('organization',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2', 'role', 'organization'),
        }),
    )

admin.site.register(User, CustomUserAdmin)
admin.site.register(Organization)
admin.site.register(Workflow)
admin.site.register(Document)