import logging
import time
import asyncio

from pyrogram import enums
from pyrogram.errors import ChatAdminRequired

logger = logging.getLogger(__name__)


async def delete_after(sent_msg, delay):
    await asyncio.sleep(delay)
    try:
        await sent_msg.delete()
    except Exception as e:
        logger.warning("Failed to delete FSUB message: %s", e)


async def check_fsub(
    client, message, chat_id, db,
    script, temp, is_subscribed, AUTH_CHANNEL, ADMINS, WAIT_TIME=300
): 
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    mychannel = AUTH_CHANNEL
    mylink = await db.get_link("auth_channel", mychannel)

    if not mylink:
        return False

    if isinstance(mylink, (int, str)):
        mylink = [int(mylink)]

    mylink = [int(channel_id) for channel_id in mylink]

    user_id = message.from_user.id

    # ADMINS and group admins need to join only the first channel.
    is_admin = user_id in ADMINS

    if not is_admin and chat_id:
        try:
            member = await client.get_chat_member(
                int(chat_id), user_id
            )
            is_admin = member.status in (
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.OWNER
            )
        except Exception as e:
            logger.debug("Group admin check failed: %s", e)

    if is_admin:
        mylink = mylink[:1]

    # Find channels the user has not joined.
    not_joined = []

    for channel_id in mylink:
        if not await is_subscribed(client, message, channel_id):
            not_joined.append(channel_id)

    if not not_joined:
        return False

    # Check the latest join-request timestamp.
    latest_request_time = None

    for channel_id in mylink:
        request = await db.get_join_request(user_id, channel_id)

        if not request:
            continue

        request_time = request.get("request_time")

        if request_time is None:
            continue

        try:
            request_time = int(request_time)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid join-request timestamp for user %s, channel %s",
                user_id, channel_id
            )
            continue

        if latest_request_time is None or request_time > latest_request_time:
            latest_request_time = request_time

    if latest_request_time is not None:
        elapsed = int(time.time()) - latest_request_time
        if elapsed < WAIT_TIME:
            return False

    # Show the first channel the user has not joined.
    channel_id = not_joined[0]

    try:
        invite_link = await client.create_chat_invite_link(
            channel_id,
            creates_join_request=True
        )

    except ChatAdminRequired:
        logger.error("Bot is not admin in channel: %s", channel_id)

        await client.send_message(
            chat_id=user_id,
            text="❌ Bot is not admin in the updates channel."
        )
        return True

    except Exception as e:
        logger.exception(
            "Failed to create invite link for %s: %s",
            channel_id, e
        )

        await client.send_message(
            chat_id=user_id,
            text="❌ Could not create the channel invite link."
        )
        return True

    btn = [[
        InlineKeyboardButton(
            "📢 Join Updates Channel",
            url=invite_link.invite_link
        )
    ]]

    # Preserve the original start payload for Try Again.
    command = getattr(message, "command", [])

    if len(command) > 1:
        btn.append([
            InlineKeyboardButton(
                "🔄 Try Again",
                url=f"https://t.me/{temp.U_NAME}?start={command[1]}"
            )
        ])
    else:
        btn.append([
            InlineKeyboardButton(
                "🔄 Try Again",
                url=f"https://t.me/{temp.U_NAME}?start=subscribe"
            )
        ])

    sent_msg = await client.send_message(
        chat_id=user_id,
        text=script.FSUB_TXT,
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.MARKDOWN
    )

    asyncio.create_task(delete_after(sent_msg, 20))

    return True
