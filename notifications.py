"""Format Avito message into a Telegram notification."""


def build_notification(account: dict, chat: dict, message: dict) -> str:
    """
    account  — row from avito_accounts
    chat     — chat object from Avito API
    message  — message object from Avito API
    """
    acc_name = account.get("name", "—")
    acc_phone = account.get("avito_phone", "")
    if acc_phone:
        acc_label = f"{acc_name}({acc_phone})"
    else:
        acc_label = acc_name

    # Sender name
    author = message.get("author", {})
    sender_name = author.get("name") or "Неизвестный"

    # Item (object/listing)
    item = chat.get("context", {}).get("value", {})
    item_title = item.get("title") or chat.get("subject") or "—"

    # Message text
    content = message.get("content", {})
    msg_text = content.get("text") or "[медиа]"

    return (
        "🔔 <b>Уведомление от Авито:</b>\n\n"
        f"👤 <b>Авито аккаунт:</b> {acc_label}\n\n"
        f"👥 <b>От пользователя:</b> {sender_name}\n\n"
        f"📦 <b>Объявление:</b> {item_title}\n\n"
        f"💬 <b>Сообщение:</b>\n{msg_text}"
    )
