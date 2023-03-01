from rest_framework.pagination import PageNumberPagination


class MessagePagination(PageNumberPagination):
    page_size = 5
    page_size_query_description = "page_size"
    max_page_size = 100
