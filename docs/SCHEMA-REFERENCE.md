# 🗄 مرجع اسکیمای دیتابیس (تولید خودکار از database.py)

کل تیبل‌ها: **34** · کل توابع async: **135**


## تیبل‌ها

### `users`
ستون‌ها: `user_id`, `username`, `first_name`, `credits`, `total_earned`, `total_spent`, `products_sold`, `created_at`, `'now'))`, `is_banned`

### `tasks`
ستون‌ها: `id`, `title`, `description`, `task_type`, `target_url`, `credits_reward`, `max_completions`, `current_completions`, `creator_id`, `is_active`, `created_at`, `'now'))`

### `task_completions`
ستون‌ها: `id`, `task_id`, `user_id`, `proof`, `status`, `completed_at`, `'now'))`, `verified_at`

### `products`
ستون‌ها: `id`, `creator_id`, `title`, `description`, `price_credits`, `price_usd`, `file_path`, `file_type`, `preview_path`, `category`, `tags`, `sales_count`, `is_active`, `created_at`, `'now'))`

### `purchases`
ستون‌ها: `id`, `buyer_id`, `product_id`, `price_credits`, `purchased_at`, `'now'))`

### `ad_campaigns`
ستون‌ها: `id`, `advertiser_id`, `title`, `description`, `target_follows`, `target_channel`, `credits_per_follow`, `total_budget`, `spent_budget`, `is_active`, `created_at`, `'now'))`

### `transactions`
ستون‌ها: `id`, `user_id`, `amount`, `tx_type`, `reference_id`, `description`, `created_at`, `'now'))`

### `hermes_sessions`
ستون‌ها: `user_id`, `session_id`, `updated_at`, `'now'))`

### `deposits`
ستون‌ها: `id`, `user_id`, `network`, `txid`, `amount_usdt`, `status`, `reviewed_by`, `created_at`, `'now'))`, `reviewed_at`, `txid)`

### `withdrawals`
ستون‌ها: `id`, `user_id`, `network`, `address`, `amount_usdt`, `fee_usdt`, `status`, `reviewed_by`, `created_at`, `'now'))`, `reviewed_at`

### `ref_milestones`
ستون‌ها: `user_id`, `threshold`, `awarded_at`, `'now'))`, `threshold)`

### `coupons`
ستون‌ها: `id`, `code`, `owner_id`, `percent`, `max_uses`, `uses`, `active`, `created_at`, `'now'))`

### `role_audit`
ستون‌ها: `id`, `user_id`, `old_role`, `new_role`, `granted_by`, `created_at`, `'now'))`

### `content_pages`
ستون‌ها: `key`, `title`, `body`, `updated_by`, `updated_at`, `'now'))`

### `settings`
ستون‌ها: `key`, `value`, `updated_by`, `updated_at`, `'now'))`

### `custom_bots`
ستون‌ها: `user_id`, `api_key`, `base_url`, `model`, `active`, `created_at`, `'now'))`

### `chat_messages`
ستون‌ها: `id`, `session_id`, `user_id`, `role`, `'assistant'))`, `content`, `created_at`, `'now'))`

### `sessions`
ستون‌ها: `id`, `user_id`, `title`, `created_at`, `'now'))`, `last_active`, `'now'))`

### `kb_notes`
ستون‌ها: `id`, `user_id`, `topic`, `content`, `source`, `created_at`, `'now'))`

### `cron_tasks`
ستون‌ها: `id`, `owner_id`, `hour`, `minute`, `text`, `active`, `last_date`, `created_at`, `'now'))`

### `reviews`
ستون‌ها: `id`, `product_id`, `buyer_id`, `stars`, `created_at`, `'now'))`

### `promo_codes`
ستون‌ها: `code`, `credits`, `max_uses`, `used_count`, `created_by`, `expires_at`, `created_at`, `'now'))`

### `promo_redemptions`
ستون‌ها: `code`, `user_id`, `created_at`, `'now'))`, `user_id)`

### `tickets`
ستون‌ها: `id`, `user_id`, `category`, `subject`, `status`, `created_at`, `'now'))`, `updated_at`, `'now'))`

### `ticket_msgs`
ستون‌ها: `id`, `ticket_id`, `sender_id`, `sender_role`, `body`, `created_at`, `'now'))`

### `quests`
ستون‌ها: `id`, `title`, `quest_type`, `target`, `reward_credits`, `active`

### `quest_claims`
ستون‌ها: `quest_id`, `user_id`, `claimed_at`, `'now'))`, `user_id)`

### `reports`
ستون‌ها: `id`, `reporter_id`, `target`, `reason`, `status`, `created_at`, `'now'))`

### `hunter_permissions`
ستون‌ها: `user_id`, `can_moderate_products`, `can_review_deposits`, `can_review_withdrawals`, `can_ban_users`, `can_broadcast`, `can_manage_skills`, `can_view_analytics`, `granted_by`, `created_at`, `'now'))`

### `user_memories`
ستون‌ها: `id`, `user_id`, `kind`, `content`, `importance`, `source`, `dedup_key`, `recall_count`, `last_recalled_at`, `created_at`, `'now'))`, `dedup_key)`

### `user_profile`
ستون‌ها: `user_id`, `interests`, `buys_count`, `total_spent_credits`, `last_categories`, `persona`, `persona_at`, `updated_at`, `'now'))`

### `follows`
ستون‌ها: `follower_id`, `target_id`, `created_at`, `'now'))`, `target_id)`

### `product_engagement`
ستون‌ها: `product_id`, `user_id`, `type`, `created_at`, `'now'))`, `user_id`, `type)`

### `product_comments`
ستون‌ها: `id`, `product_id`, `user_id`, `text`, `created_at`, `'now'))`


## توابع database.py

| تابع | آرگومان‌ها |
|---|---|
| `init_db` |  |
| `_singleton` |  |
| `_acquire` | tuned: bool |
| `_session` | tuned: bool |
| `get_db` |  |
| `raw_db` |  |
| `close_pool` |  |
| `snapshot_to` | dest_path: str |
| `get_user` | user_id: int |
| `create_user` | user_id: int, username: str = None, first_name: str = None |
| `update_credits` | user_id: int, amount: int, tx_type: str, description: str = "", reference_id: int = None |
| `get_leaderboard` | limit: int = 10 |
| `get_user_stats` | user_id: int |
| `search_products` | query: str = "", category: str = "", limit: int = 20, offset: int = 0 |
| `get_product` | product_id: int |
| `get_pending_tasks` | limit: int = 10 |
| `get_user_tasks` | user_id: int, status: str = None |
| `get_my_products` | user_id: int |
| `get_purchased_products` | user_id: int |
| `get_active_campaigns` | limit: int = 10 |
| `is_task_completed_by_user` | task_id: int, user_id: int |
| `is_product_purchased_by_user` | product_id: int, user_id: int |
| `get_all_users_count` |  |
| `get_total_products` |  |
| `get_total_sales` |  |
| `get_hermes_session` | user_id: int |
| `set_hermes_session` | user_id: int, session_id: str |
| `is_banned` | user_id: int |
| `try_hold_credits` | user_id: int, credits: int, tx_type: str, description: str |
| `product_rating` | product_id: int |
| `add_review` | product_id: int, buyer_id: int, stars: int |
| `list_pending_products` | limit: int = 10 |
| `count_pending_products` |  |
| `set_product_status` | product_id: int, status: str, reviewed_by: int |
| `set_referred_by` | user_id: int, referrer_id: int |
| `get_referrer` | user_id: int |
| `mark_ref_bonus_paid` | user_id: int |
| `count_qualified_refs` | referrer_id: int |
| `count_total_refs` | referrer_id: int |
| `list_top_referrers` | limit: int = 5 |
| `is_milestone_awarded` | user_id: int, threshold: int |
| `award_ref_milestone` | user_id: int, threshold: int |
| `get_hunter_perms` | user_id: int |
| `set_hunter_perm` | user_id: int, perm_key: str, value: bool, granted_by: int |
| `delete_hunter` | user_id: int |
| `get_role` | user_id: int |
| `delete_product` | product_id: int, creator_id: int |
| `set_role` | user_id: int, new_role: str, granted_by: int, domain: str | None = None |
| `get_domain` | user_id: int |
| `category_stats` | category: str |
| `category_products` | category: str, limit: int = 8, include_inactive: bool = True |
| `set_product_flag` | product_id: int, column: str, value: int, category: str |
| `capo_team_stats` | capo_id: int |
| `create_coupon` | owner_id: int, code: str, percent: int, max_uses: int |
| `get_coupon` | code: str |
| `get_coupon_by_id` | coupon_id: int |
| `redeem_coupon` | coupon_id: int |
| `get_setting` | key: str, default: str | None = None |
| `set_setting` | key: str, value: str | None, updated_by: int | None = None |
| `ban_user` | user_id: int, banned: bool |
| `update_product_field` | product_id: int, column: str, value |
| `upsert_custom_bot` | user_id: int, api_key: str, base_url: str, model: str, active: int = 1 |
| `get_custom_bot` | user_id: int |
| `set_custom_bot_active` | user_id: int, active: bool |
| `mem_add` | user_id: int, role: str, content: str |
| `mem_recent` | user_id: int, turns: int = MEMORY_TURNS |
| `mem_count` | user_id: int |
| `mem_clear` | user_id: int |
| `history_search` | user_id: int, query: str, limit: int = 8 |
| `reminder_add` | owner_id: int, hour: int, minute: int, text: str |
| `reminder_list` | owner_id: int |
| `reminder_delete` | owner_id: int, task_id: int |
| `due_reminders` | now_h: int, now_m: int, today: str, limit: int = 50 |
| `kb_save` | user_id: int, topic: str, content: str, source: str = "librarian" |
| `kb_search` | user_id: int, query: str, limit: int = 2 |
| `kb_count` | user_id: int |
| `seed_content` |  |
| `get_content` | key: str |
| `save_content` | key: str, body: str, updated_by: int |
| `seed_products` |  |
| `create_deposit` | user_id: int, network: str, txid: str, amount_usdt: float |
| `get_deposit` | deposit_id: int |
| `set_deposit_status` | deposit_id: int, status: str, reviewed_by: int |
| `list_pending_deposits` | limit: int = 10 |
| `list_user_deposits` | user_id: int, limit: int = 10 |
| `create_withdrawal` | user_id: int, network: str, address: str,                             amount_usdt: float, fee_usdt: float |
| `get_withdrawal` | wd_id: int |
| `set_withdrawal_status` | wd_id: int, status: str, reviewed_by: int |
| `list_pending_withdrawals` | limit: int = 10 |
| `list_user_withdrawals` | user_id: int, limit: int = 10 |
| `record_deposit_verification_attempt` | deposit_id: int, reason: str = "" |
| `approve_verified_deposit` | deposit_id: int, reviewed_by: int = 0 |
| `mark_withdrawal_paid` | wd_id: int, txid: str, reviewed_by: int = 0 |
| `record_payout_error` | wd_id: int, reason: str |
| `approve_deposit_manual` | deposit_id: int, reviewed_by: int = 0 |
| `reject_withdrawal_and_refund` | wd_id: int, reviewed_by: int = 0 |
| `db_size_bytes` |  |
| `db_counts` |  |
| `chat_sweep_dormant` | days: int = None, min_earned: int = 0 |
| `archive_old_transactions` | days: int = None, keep: int = 5000 |
| `vacuum_now` |  |
| `growth_stats` |  |
| `top_sellers` | limit: int = 10 |
| `product_health` |  |
| `revenue_30d` | days: int = 30 |
| `count_pending_task_reviews` |  |
| `get_task_review_queue` | limit: int = 20 |
| `get_task_review_item` | cid: int |
| `review_task_approve` | cid: int |
| `review_task_reject` | cid: int |
| `daily_bonus_state` | user_id: int |
| `claim_daily_bonus` | user_id: int, base: int = 15, step: int = 5, cap: int = 50 |
| `upsert_rate` | product_id: int, buyer_id: int, stars: int |
| `create_promo` | code: str, credits: int, max_uses: int, days: int, created_by: int |
| `redeem_promo` | code: str, user_id: int |
| `list_promos` | limit: int = 10 |
| `pick_inactive_users` | days: int, limit: int = 1000 |
| `pick_random_active_users` | days: int, n: int |
| `create_ticket` | user_id: int, category: str, subject: str, body: str |
| `add_ticket_msg` | ticket_id: int, sender_id: int, role: str, body: str |
| `list_user_tickets` | user_id: int, limit: int = 8 |
| `get_ticket` | ticket_id: int |
| `ticket_thread` | ticket_id: int, limit: int = 8 |
| `list_open_tickets` | limit: int = 10 |
| `set_ticket_status` | ticket_id: int, status: str |
| `ensure_default_quests` |  |
| `user_metrics` | user_id: int |
| `quests_view` | user_id: int |
| `claim_quest` | quest_id: int, user_id: int |
| `xp_snapshot` | user_id: int |
| `create_report` | reporter_id: int, target: str, reason: str |
| `list_open_reports` | limit: int = 10 |
| `user_analytics` | user_id: int |
| `seller_analytics` | seller_id: int |
| `leaderboard` | kind: str = "xp", days: int = 0, limit: int = 10 |