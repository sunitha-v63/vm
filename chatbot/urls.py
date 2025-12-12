# from django.urls import path
# from . import views

# urlpatterns = [
#     path("", views.chat_page, name="chat_page"),
#     path("api/chat/", views.chat_api),
#     path("api/conversations/", views.all_conversations),
#     path("api/messages/<int:cid>/", views.conversation_messages),
#     path("api/delete/<int:cid>/", views.delete_conversation),
#     path("api/restore/<int:cid>/", views.restore_conversation),
#     path("api/rename/<int:cid>/", views.rename_conversation),
#     path("api/pin/<int:cid>/", views.pin_conversation),
#     path("api/upload-file/", views.upload_file),
#     path("api/delete-message/<int:mid>/", views.delete_message), 
# ]

from django.urls import path
from . import views

urlpatterns = [
    path("chat/", views.chat_api, name="chat_api"),
    path("conversations/", views.all_conversations, name="all_conversations"),
    path("messages/<int:cid>/", views.conversation_messages, name="conversation_messages"),
    path("delete/<int:cid>/", views.delete_conversation, name="delete_conversation"),
    path("restore/<int:cid>/", views.restore_conversation, name="restore_conversation"),
    path("rename/<int:cid>/", views.rename_conversation, name="rename_conversation"),
    path("pin/<int:cid>/", views.pin_conversation, name="pin_conversation"),
    path("upload-file/", views.upload_file, name="upload_file"),
    path("delete-message/<int:mid>/", views.delete_message, name="delete_message"),
]





