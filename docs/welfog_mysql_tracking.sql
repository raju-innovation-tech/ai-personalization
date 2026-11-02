-- =====================================================================
-- Welfog -> AI Personalization Engine : tracking additions (MySQL)
--
-- RUN ON : the MySQL database (welfog_db_mysql).
-- POSTGRES: nothing to change (it only holds the product catalog).
--
-- Rules
--  * Note the moment you run section 3 (triggers): put that UTC time (with the +00:00 offset) in WELFOG_EVENTS_TABLE_START
--    on the AI side so cart / wishlist rows are not counted twice.
--  * Run on STAGING first.
--  * Store every timestamp in UTC.
--  * user_id    = customers.user_id   (NOT customers.id)
--  * product_id = Postgres products.pro_id   (NOT products.id)
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) One event-log table for all missing behaviour events
--    event_type values used:
--      PRODUCT_VIEW, CATEGORY_VIEW, PRODUCT_SEARCH, CHECKOUT_STARTED,
--      REMOVE_FROM_CART, WISHLIST_REMOVE   (+ ADD_TO_CART, WISHLIST_ADD via triggers below)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_events` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`       INT NULL            COMMENT 'customers.user_id (NULL for guests)',
  `guest_id`      VARCHAR(255) NULL   COMMENT 'anonymous id for not-logged-in users (e.g. carts.temp_user_id)',
  `event_type`    VARCHAR(32) NOT NULL,
  `product_id`    BIGINT NULL         COMMENT 'Postgres products.pro_id',
  `category_id`   INT NULL,
  `search_query`  VARCHAR(500) NULL,
  `session_id`    VARCHAR(128) NULL,
  `platform`      VARCHAR(10) NOT NULL DEFAULT 'unknown' COMMENT 'web | android | ios | unknown',
  `metadata`      JSON NULL,
  `occurred_at`   DATETIME(3) NOT NULL COMMENT 'UTC',
  `created_at`    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ue_user_time` (`user_id`, `occurred_at`),
  KEY `idx_ue_type_time` (`event_type`, `occurred_at`),
  KEY `idx_ue_product`   (`product_id`),
  KEY `idx_ue_session`   (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- 2) session_id + platform on orders and carts
--    NOTE: `orders` is PARTITIONED BY RANGE (created_at). ALGORITHM=INSTANT may not be
--    supported on a partitioned table and a plain ALTER can rebuild it, so run the `orders`
--    statement on STAGING first, then during low traffic (or with gh-ost / pt-online-schema-change).
--    `carts` is not partitioned; INSTANT needs MySQL 8.0.12+ (remove it on older versions).
-- ---------------------------------------------------------------------
ALTER TABLE `orders`
  ADD COLUMN `session_id` VARCHAR(128) NULL,
  ADD COLUMN `platform`   VARCHAR(10)  NULL COMMENT 'web | android | ios';

ALTER TABLE `carts`
  ADD COLUMN `session_id` VARCHAR(128) NULL,
  ADD COLUMN `platform`   VARCHAR(10)  NULL COMMENT 'web | android | ios',
  ALGORITHM=INSTANT;

-- The application must now fill orders.session_id / orders.platform when an
-- order is created, and carts.session_id / carts.platform when an item is added.


-- ---------------------------------------------------------------------
-- 3) Triggers (no app change needed): cart add + wishlist add/remove history.
--    The CONTINUE HANDLER makes sure a logging error can never break a
--    customer's cart/wishlist action.
-- ---------------------------------------------------------------------
DELIMITER $$

CREATE TRIGGER `trg_carts_ai_event` AFTER INSERT ON `carts`
FOR EACH ROW
BEGIN
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION BEGIN END;
  INSERT INTO `user_events`
    (`user_id`, `guest_id`, `event_type`, `product_id`, `session_id`, `platform`, `metadata`, `occurred_at`)
  VALUES
    (NEW.`user_id`, NULLIF(NEW.`temp_user_id`, ''), 'ADD_TO_CART', NEW.`product_id`,
     NEW.`session_id`, COALESCE(NEW.`platform`, 'unknown'),
     JSON_OBJECT('quantity', NEW.`quantity`, 'price', NEW.`price`),
     UTC_TIMESTAMP(3));
END$$

CREATE TRIGGER `trg_wishlists_ai_event` AFTER INSERT ON `wishlists`
FOR EACH ROW
BEGIN
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION BEGIN END;
  INSERT INTO `user_events` (`user_id`, `event_type`, `product_id`, `platform`, `occurred_at`)
  VALUES (NEW.`user_id`, 'WISHLIST_ADD', NEW.`product_id`, 'unknown', UTC_TIMESTAMP(3));
END$$

CREATE TRIGGER `trg_wishlists_ad_event` AFTER DELETE ON `wishlists`
FOR EACH ROW
BEGIN
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION BEGIN END;
  INSERT INTO `user_events` (`user_id`, `event_type`, `product_id`, `platform`, `occurred_at`)
  VALUES (OLD.`user_id`, 'WISHLIST_REMOVE', OLD.`product_id`, 'unknown', UTC_TIMESTAMP(3));
END$$

DELIMITER ;

-- NOTE: there is intentionally NO delete trigger on `carts`. Cart rows are
-- probably also deleted after checkout, which would create fake "removed from
-- cart" events. REMOVE_FROM_CART must be logged by the application (section 4).


-- ---------------------------------------------------------------------
-- 4) Events the APPLICATION must insert (website + mobile app backend)
--    ? = value from the request.  Always send UTC time.
-- ---------------------------------------------------------------------

-- 4a) Product page opened
INSERT INTO `user_events` (`user_id`, `guest_id`, `event_type`, `product_id`, `category_id`, `session_id`, `platform`, `occurred_at`)
VALUES (?, ?, 'PRODUCT_VIEW', ?, ?, ?, ?, UTC_TIMESTAMP(3));

-- 4b) Category page opened
INSERT INTO `user_events` (`user_id`, `guest_id`, `event_type`, `category_id`, `session_id`, `platform`, `occurred_at`)
VALUES (?, ?, 'CATEGORY_VIEW', ?, ?, ?, UTC_TIMESTAMP(3));

-- 4c) User searched (keep your existing global `searches` table as it is)
INSERT INTO `user_events` (`user_id`, `guest_id`, `event_type`, `search_query`, `session_id`, `platform`, `occurred_at`)
VALUES (?, ?, 'PRODUCT_SEARCH', ?, ?, ?, UTC_TIMESTAMP(3));

-- 4d) Checkout started (one row per product in the cart, or one row with product_id NULL)
INSERT INTO `user_events` (`user_id`, `guest_id`, `event_type`, `product_id`, `session_id`, `platform`, `occurred_at`)
VALUES (?, ?, 'CHECKOUT_STARTED', ?, ?, ?, UTC_TIMESTAMP(3));

-- 4e) Item removed from cart by the user (NOT when the cart is cleared after an order)
INSERT INTO `user_events` (`user_id`, `guest_id`, `event_type`, `product_id`, `session_id`, `platform`, `occurred_at`)
VALUES (?, ?, 'REMOVE_FROM_CART', ?, ?, ?, UTC_TIMESTAMP(3));


-- ---------------------------------------------------------------------
-- 5) Read-only access for the AI engine (replace the placeholders)
-- ---------------------------------------------------------------------
-- CREATE USER 'ai_engine_ro'@'<AI_SERVER_IP>' IDENTIFIED BY '<strong-password>';
-- GRANT SELECT ON `<mysql_database_name>`.* TO 'ai_engine_ro'@'<AI_SERVER_IP>';


-- ---------------------------------------------------------------------
-- 6) Optional cleanup (run weekly). The engine looks back up to 365 days,
--    so keep at least that much.
-- ---------------------------------------------------------------------
-- DELETE FROM `user_events` WHERE `occurred_at` < UTC_TIMESTAMP() - INTERVAL 400 DAY LIMIT 50000;
