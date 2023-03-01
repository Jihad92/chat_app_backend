import json
from uuid import UUID

from channels.generic.websocket import JsonWebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

from .models import Conversation, Message
from .api.serializers import MessageSerializer


User = get_user_model()


class UUIDEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, UUID):
            return o.hex
        return json.JSONEncoder(self, o)


class ChatConsumer(JsonWebsocketConsumer):
    """
    This consumer is used to show user's online status,
    and send notifications.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.conversation_name = None
        self.conversation = None

    def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            return

        self.accept()
        self.conversation_name = (
            f"{self.scope ['url_route']['kwargs']['conversation_name']}"
        )
        self.conversation, created = Conversation.objects.get_or_create(
            name=self.conversation_name
        )

        async_to_sync(self.channel_layer.group_add)(
            self.conversation_name, self.channel_name
        )

        self.send_json(
            {
                "type": "online_user_list",
                "users": [user.username for user in self.conversation.online.all()],
            }
        )
        async_to_sync(self.channel_layer.group_send)(
            self.conversation_name,
            {
                "type": "user_join",
                "user": self.user.username,
            },
        )
        self.conversation.online.add(self.user)

        messages = self.conversation.messages.all().order_by("-timestamp")[0:10]
        message_count = self.conversation.messages.all().count()
        self.send_json(
            {
                "type": "last_50_messages",
                "messages": MessageSerializer(messages, many=True).data,
                "hasMore": message_count > 10,
            }
        )

    def disconnect(self, code):
        if self.user.is_authenticated:
            async_to_sync(self.channel_layer.group_send)(
                self.conversation_name,
                {
                    "type": "user_leave",
                    "user": self.user.username,
                },
            )
            self.conversation.online.remove(self.user)
        return super().disconnect(code)

    def receive_json(self, content, **kwargs):
        message_type = content["type"]
        if message_type == "read_messages":
            messages_to_me = self.conversation.messages.filter(to_user=self.user)
            messages_to_me.update(read=True)
            unread_count = Message.objects.filter(to_user=self.user, read=False).count()
            async_to_sync(self.channel_layer.group_send)(
                self.user.username + "__notifications",
                {
                    "type": "unread_count",
                    "unread_count": unread_count,
                },
            )
        elif message_type == "typing":
            async_to_sync(self.channel_layer.group_send)(
                self.conversation_name,
                {
                    "type": "typing",
                    "uesr": self.user.username,
                    "typing": content["typing"],
                },
            )
        elif message_type == "chat_message":
            message = Message.objects.create(
                from_user=self.user,
                to_user=self.get_reciever(),
                content=content["message"],
                conversation=self.conversation,
            )

            notification_group_name = self.get_reciever().username + "__notifications"
            async_to_sync(self.channel_layer.group_send)(
                notification_group_name,
                {
                    "type": "new_message_notification",
                    "name": self.user.username,
                    "message": MessageSerializer(message).data,
                },
            )
            async_to_sync(self.channel_layer.group_send)(
                self.conversation_name,
                {
                    "type": "chat_message_echo",
                    "name": self.user.username,
                    "message": MessageSerializer(message).data,
                },
            )
        return super().receive_json(content, **kwargs)

    def unread_count(self, event):
        self.send_json(event)

    def typing(self, event):
        self.send_json(event)

    def user_join(self, event):
        self.send_json(event)

    def user_leave(self, event):
        self.send_json(event)

    def get_reciever(self):
        usernames = self.conversation_name.split("__")
        for username in usernames:
            if username != self.user.username:
                return User.objects.get(username=username)

    def chat_message_echo(self, event):
        self.send_json(event)

    def new_message_notification(self, event):
        self.send_json(event)

    @classmethod
    def encode_json(cls, content):
        return json.dumps(content, cls=UUIDEncoder)


class NotificationConsumer(JsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.notification_group_name = None

    def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            return

        self.accept()
        self.notification_group_name = self.user.username + "__notifications"
        async_to_sync(self.channel_layer.group_add)(
            self.notification_group_name,
            self.channel_name,
        )
        unread_count = Message.objects.filter(to_user=self.user, read=False).count()
        self.send_json({"type": "unread_count", "unread_count": unread_count})

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.notification_group_name,
            self.channel_name,
        )
        return super().disconnect(code)

    def new_message_notification(self, event):
        self.send_json(event)

    def unread_count(self, event):
        self.send_json(event)
