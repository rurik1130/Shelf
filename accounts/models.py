from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    REQUIRED_FIELDS: ClassVar[list[str]] = ["email"]
