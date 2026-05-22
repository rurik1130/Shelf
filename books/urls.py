from django.urls import path

from . import views

app_name = "books"

urlpatterns = [
    path("", views.book_list, name="book_list"),
    path("<int:id>/", views.book_detail, name="book_detail"),
    path("create/", views.book_create, name="book_create"),
    path("<int:id>/edit/", views.book_update, name="book_update"),
    path("<int:id>/delete/", views.book_delete, name="book_delete"),
    path("delete/done/", views.book_delete_complete, name="book_delete_complete"),
    path("isbn-lookup/", views.isbn_lookup, name="isbn_lookup"),
    path("locations/", views.location_list, name="location_list"),
    path("location/create/", views.location_create, name="location_create"),
    path("locations/<int:id>/update/", views.location_update, name="location_update"),
    path("locations/<int:id>/delete/", views.location_delete, name="location_delete"),
    path("<int:id>/borrow/", views.borrow_book, name="borrow_book"),
    path("borrows/<int:id>/complete/", views.borrow_complete, name="borrow_complete"),
    path("<int:id>/reserve/", views.reserve_book, name="reserve_book"),
    path(
        "reservations/<int:id>/complete/",
        views.reserve_complete,
        name="reserve_complete",
    ),
    path(
        "<int:id>/reservation/cancel/",
        views.cancel_reservation,
        name="cancel_reservation",
    ),
    path("<int:id>/return/", views.return_book, name="return_book"),
    path("borrows/<int:id>/return/", views.return_complete, name="return_complete"),
    path("<int:id>/review/", views.add_review, name="add_review"),
    path("reviews/<int:id>/delete/", views.delete_review, name="delete_review"),
    path(
        "reviews/delete/done/",
        views.review_delete_complete,
        name="review_delete_complete",
    ),
    path("mypage/", views.mypage, name="mypage"),
]
