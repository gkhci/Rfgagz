from ultra_panel_core import *
from telegram.ext import ConversationHandler

# =========================
#   CONVERSATION STATES
# =========================
(
    MAIN_MENU,
    NEW_INBOUND_REMARK,
    NEW_INBOUND_HOST,
    NEW_INBOUND_PORT,
    NEW_INBOUND_PROTOCOL,
    NEW_INBOUND_SECURITY,
    NEW_INBOUND_NETWORK,
    EDIT_INBOUND,
    CONFIRM_DELETE,
    USERS_LIST,
    USER_DETAILS,
    BATCH_IMPORT
) = range(11)

# =========================
#   UI COMPONENTS
# =========================
class UltraUI:
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📡 مدیریت اینباوندها", callback_data="menu_inbounds"),
                InlineKeyboardButton("👥 مدیریت کاربران", callback_data="menu_users")
            ],
            [
                InlineKeyboardButton("📊 آمار و گزارشات", callback_data="menu_stats"),
                InlineKeyboardButton("⚡ ساخت سریع کانفیگ", callback_data="menu_quick_config")
            ],
            [
                InlineKeyboardButton("📦 واردات انبوه", callback_data="menu_batch_import"),
                InlineKeyboardButton("🔍 جستجوی پیشرفته", callback_data="menu_search")
            ],
            [
                InlineKeyboardButton("🔄 پشتیبان‌گیری", callback_data="menu_backup"),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")
            ]
        ])
    
    @staticmethod
    def inbounds_menu(inbounds: List[Inbound], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
        rows = []
        start = page * page_size
        end = min(start + page_size, len(inbounds))
        
        for inb in inbounds[start:end]:
            status_emoji = "🟢" if inb.status == "active" else "🔴"
            rows.append([
                InlineKeyboardButton(
                    f"{status_emoji} {inb.remark} [{inb.protocol}]", 
                    callback_data=f"view_inbound:{inb.id}"
                )
            ])
        
        # Navigation
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"inbound_page:{page-1}"))
        if end < len(inbounds):
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"inbound_page:{page+1}"))
        if nav_buttons:
            rows.append(nav_buttons)
        
        rows.append([InlineKeyboardButton("➕ اینباوند جدید", callback_data="new_inbound")])
        rows.append([InlineKeyboardButton("⬅️ بازگشت به منو", callback_data="back_main")])
        
        return InlineKeyboardMarkup(rows)
    
    @staticmethod
    def inbound_detail_menu(inb: Inbound) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ کانفیگ‌ها", callback_data=f"build_config:{inb.id}"),
                InlineKeyboardButton("🎨 QR کد", callback_data=f"qr_config:{inb.id}")
            ],
            [
                InlineKeyboardButton("📋 سابسکریپشن", callback_data=f"subscription:{inb.id}"),
                InlineKeyboardButton("📊 ترافیک", callback_data=f"traffic:{inb.id}")
            ],
            [
                InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit_inbound:{inb.id}"),
                InlineKeyboardButton("🔄 تغییر وضعیت", callback_data=f"toggle_status:{inb.id}")
            ],
            [
                InlineKeyboardButton("🗑 حذف", callback_data=f"delete_inbound:{inb.id}")
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_inbounds")]
        ])

# =========================
#   BOT HANDLERS
# =========================
class UltraPanelBot:
    def __init__(self):
        self.storage = UltraStorage()
        self.config_builder = ConfigBuilder()
        self.security = SecurityManager()
        self.analytics = Analytics()
        self.app = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not SecurityManager.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ شما دسترسی ادمین ندارید!")
            return
        
        # ثبت کاربر
        users = await self.storage.get_users()
        user_id = str(update.effective_user.id)
        if not any(u.id == user_id for u in users):
            users.append(User(
                id=user_id,
                username=update.effective_user.username or "",
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name or ""
            ))
            await self.storage.save_users(users)
        
        await update.message.reply_text(
            "🌟 <b>REZA GROOTZ ULTRA PANEL</b>\n"
            "نسخه فوق پیشرفته پنل مدیریتی تلگرام\n"
            f"📊 تعداد اینباوندها: {len(await self.storage.get_inbounds())}\n"
            "برای شروع از منو استفاده کنید.",
            parse_mode="HTML",
            reply_markup=UltraUI.main_menu()
        )
    
    async def menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "back_main":
            await query.message.edit_text(
                "🏛 منوی اصلی",
                reply_markup=UltraUI.main_menu()
            )
        
        elif data == "menu_inbounds":
            inbounds = await self.storage.get_inbounds()
            await query.message.edit_text(
                f"📡 لیست اینباوندها ({len(inbounds)})",
                reply_markup=UltraUI.inbounds_menu(inbounds)
            )
        
        elif data.startswith("inbound_page:"):
            page = int(data.split(":")[1])
            inbounds = await self.storage.get_inbounds()
            await query.message.edit_reply_markup(
                reply_markup=UltraUI.inbounds_menu(inbounds, page)
            )
        
        elif data.startswith("view_inbound:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            text = (
                f"🛰 <b>اطلاعات اینباوند</b>\n\n"
                f"نام: {inb.remark}\n"
                f"پروتکل: {inb.protocol}\n"
                f"وضعیت: {'🟢 فعال' if inb.status == 'active' else '🔴 غیرفعال'}\n"
                f"هاست: {inb.host}\n"
                f"پورت: {inb.port}\n"
                f"UUID: <code>{inb.uuid}</code>\n"
                f"شبکه: {inb.network}\n"
                f"امنیت: {inb.security}\n"
                f"تاریخ ایجاد: {inb.created_at}\n"
                f"ترافیک مصرفی: {round(inb.used_traffic / (1024**3), 2)} GB"
            )
            await query.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=UltraUI.inbound_detail_menu(inb)
            )
        
        elif data.startswith("build_config:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            configs = ConfigBuilder.build_all_configs(inb)
            text = "⚡ <b>کانفیگ‌های آماده</b>\n\n"
            for name, cfg in configs.items():
                text += f"<b>{name}:</b>\n<code>{cfg}</code>\n\n"
            
            # ارسال به صورت فایل برای راحتی کپی
            bio = BytesIO()
            bio.write("\n\n".join(configs.values()).encode())
            bio.seek(0)
            
            await query.message.reply_document(
                InputFile(bio, filename=f"{inb.remark}_configs.txt"),
                caption="📄 کانفیگ‌ها به صورت فایل"
            )
            await query.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=UltraUI.inbound_detail_menu(inb)
            )
        
        elif data.startswith("qr_config:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            configs = ConfigBuilder.build_all_configs(inb)
            for name, cfg in configs.items():
                qr_img = ConfigBuilder.generate_qr(cfg)
                await query.message.reply_photo(
                    InputFile(qr_img, filename=f"{name}.png"),
                    caption=f"🎨 QR کد برای {name}"
                )
        
        elif data.startswith("subscription:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            sub_link = ConfigBuilder.generate_subscription(inb)
            await query.message.reply_text(
                f"📋 لینک سابسکریپشن:\n<code>{sub_link}</code>\n"
                "این لینک را در کلاینت خود وارد کنید.",
                parse_mode="HTML"
            )
        
        elif data.startswith("toggle_status:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            inb.status = "inactive" if inb.status == "active" else "active"
            await self.storage.update_inbound(inb)
            
            await query.message.edit_text(
                f"✅ وضعیت به {'🟢 فعال' if inb.status == 'active' else '🔴 غیرفعال'} تغییر یافت.",
                reply_markup=UltraUI.inbound_detail_menu(inb)
            )
        
        elif data.startswith("delete_inbound:"):
            inb_id = data.split(":")[1]
            inb = await self.storage.find_inbound(inb_id)
            if not inb:
                await query.message.reply_text("❌ اینباوند یافت نشد!")
                return
            
            await query.message.edit_text(
                f"⚠️ آیا از حذف اینباوند '{inb.remark}' مطمئن هستید؟",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"confirm_delete:{inb_id}"),
                        InlineKeyboardButton("❌ خیر، بازگشت", callback_data=f"view_inbound:{inb_id}")
                    ]
                ])
            )
        
        elif data.startswith("confirm_delete:"):
            inb_id = data.split(":")[1]
            await self.storage.delete_inbound(inb_id)
            await query.message.edit_text(
                "✅ اینباوند با موفقیت حذف شد.",
                reply_markup=UltraUI.main_menu()
            )
        
        elif data == "menu_stats":
            inbounds = await self.storage.get_inbounds()
            stats = await Analytics.get_stats(inbounds)
            
            text = (
                "📊 <b>آمار و گزارشات پنل</b>\n\n"
                f"📌 تعداد کل اینباوندها: {stats['total']}\n"
                f"🟢 فعال: {stats['active']}\n"
                f"🔴 غیرفعال: {stats['inactive']}\n"
                f"📈 ترافیک مصرفی کل: {stats['total_usage_gb']} GB\n\n"
                "<b>توزیع پروتکل‌ها:</b>\n"
                f"🔹 VLESS: {stats['protocols']['vless']}\n"
                f"🔸 VMess: {stats['protocols']['vmess']}\n"
                f"🔹 Trojan: {stats['protocols']['trojan']}\n"
                f"🔸 Shadowsocks: {stats['protocols']['shadowsocks']}"
            )
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=UltraUI.main_menu())
        
        elif data == "menu_quick_config":
            inbounds = await self.storage.get_inbounds()
            if not inbounds:
                await query.message.reply_text("❌ هیچ اینباوندی موجود نیست!")
                return
            
            # نمایش ۵ اینباوند اول
            rows = []
            for inb in inbounds[:5]:
                rows.append([
                    InlineKeyboardButton(
                        f"{inb.remark} [{inb.protocol}]",
                        callback_data=f"build_config:{inb.id}"
                    )
                ])
            rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_main")])
            
            await query.message.edit_text(
                "⚡ کانفیگ مورد نظر را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(rows)
            )
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت پیام‌های متنی"""
        text = update.message.text
        
        # در اینجا می‌توانید دستورات متنی اضافه کنید
        # مثلاً ساخت سریع اینباوند با فرمت خاص
        
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید."
            )
    
    def setup_handlers(self):
        """تنظیم هندلرها"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CallbackQueryHandler(self.menu_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
        self.app.add_error_handler(self.error_handler)
    
    def run(self):
        """اجرای ربات"""
        self.app = Application.builder().token(TOKEN).build()
        self.setup_handlers()
        
        print("🚀 ULTRA PANEL BOT RUNNING...")
        print("👤 Admin IDs:", ADMIN_IDS)
        
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

# =========================
#   ENTRY POINT
# =========================
if __name__ == "__main__":
    bot = UltraPanelBot()
    bot.run()
