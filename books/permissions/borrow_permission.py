def can_borrow(*, has_current_borrow, reservation_user_id, user_id):
    if has_current_borrow:
        return False

    if reservation_user_id is not None:
        return reservation_user_id == user_id

    return True


def can_reserve(*, has_current_borrow, has_reservation):
    if not has_current_borrow:
        return False

    if has_reservation:
        return False

    return True


def can_return(*, borrow_user_id, user_id):
    if not borrow_user_id:
        return False

    return borrow_user_id == user_id
