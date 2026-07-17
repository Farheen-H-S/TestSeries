from django.urls import path
from .views import SubjectViewSet, ChapterViewSet

urlpatterns = [
    # Subjects URL patterns
    path('subjects/', SubjectViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='subject-list-create'),
    
    path('subjects/<int:subject_id>/', SubjectViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='subject-detail'),
    
    path('subjects/<int:subject_id>/stats/', SubjectViewSet.as_view({
        'get': 'stats'
    }), name='subject-stats'),
    
    # Chapters URL patterns (Nested under Subject for list/create)
    path('subjects/<int:subject_id>/chapters/', ChapterViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='chapter-list-create'),
    
    # Chapters URL patterns (Direct by ID for update/delete/reorder)
    path('chapters/<int:chapter_id>/', ChapterViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='chapter-detail'),
    
    path('chapters/<int:chapter_id>/reorder/', ChapterViewSet.as_view({
        'post': 'reorder'
    }), name='chapter-reorder'),
]
