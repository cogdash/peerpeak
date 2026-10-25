/* ============================================================
   FEED — Alpine-компонент ленты случайных значков
   ============================================================ */
document.addEventListener('alpine:init', function () {
  var FEED_URL        = '/api/feed/badges';
  var BADGES_URL      = '/api/badges';
  var ME_URL          = '/api/me';

  var FEED_SIZE = 10;

  Alpine.data('feedPage', function () {
    var component = {
      badges: [],
      loading: true,
      error: '',

      me: null,
      /* Мои user-badges по id значка из каталога. */
      myBadgesByBadgeId: {},

      init() {
        this.bindCardPress();
        this.load();
      },

      destroy() {
        this.unbindCardPress();
      },

      async load() {
        this.loading = true;
        this.error = '';

        try {
          /* Сначала узнаём, кто смотрит ленту, чтобы база сразу исключила
             значки, которые уже есть на его странице. */
          var meRes = await apiFetch(ME_URL);
          var feedUrl = FEED_URL + '?limit=' + FEED_SIZE;
          if (meRes.ok && meRes.data && meRes.data.username) {
            feedUrl += '&exclude_username=' + encodeURIComponent(meRes.data.username);
          }

          var results = await Promise.all([apiFetch(feedUrl), apiFetch(BADGES_URL)]);
          var feedRes = results[0];

          this.applyMine(meRes, results[1]);

          if (!feedRes.ok) {
            this.fail('Не удалось загрузить значки.');
            return;
          }
          this.badges = Array.isArray(feedRes.data) ? feedRes.data : [];
        } catch (e) {
          this.fail('Нет связи с сервером.');
        } finally {
          this.loading = false;
        }
      },

      fail(message) {
        /* При неудачном обновлении старая лента остаётся на экране. */
        if (this.badges.length) {
          this.$store.toast.show(message);
        } else {
          this.error = message;
        }
      },

      /* ======================================================
         МОИ ЗНАЧКИ
         ====================================================== */
      applyMine(meRes, mineRes) {
        this.me = meRes && meRes.ok ? meRes.data : null;

        var byBadgeId = {};
        if (mineRes && mineRes.ok && Array.isArray(mineRes.data)) {
          mineRes.data.forEach(function (mb) {
            if (!mb || mb.badge_id == null) return;
            var key = String(mb.badge_id);
            var existing = byBadgeId[key];
            /* Полученный вариант важнее неполученного. */
            if (!existing || (mb.received && !existing.received)) {
              byBadgeId[key] = mb;
            }
          });
        }
        this.myBadgesByBadgeId = byBadgeId;
      },

      async refreshMine() {
        try {
          var results = await Promise.all([apiFetch(ME_URL), apiFetch(BADGES_URL)]);
          this.applyMine(results[0], results[1]);
        } catch (e) { /* тихо игнорируем: лента уже загружена */ }
      },

      myBadge(b) {
        return this.myBadgesByBadgeId[String(b.id)] || null;
      },

      /* ======================================================
         ОБЩАЯ КАРТОЧКА
         ====================================================== */
      get cards() {
        var self = this;

        return this.badges.map(function (b) {
          var mine = self.myBadge(b);

          return {
            key: String(b.id),
            badge_id: b.id,
            user_badge_id: mine ? mine.id : null,
            title: b.title,
            emoji: b.emoji,
            polarity: b.polarity,
            added: !!mine,
            received: !!(mine && mine.received),
            editable: false,
            creator_username: b.creator_username,
            received_at: mine ? mine.received_at : null,
            href: '/badge/' + encodeURIComponent(b.id),
            show_status: true,
            received_count: b.received_count || 0,
            users_count: b.users_count || 0
          };
        });
      },

      /* После действий обновляем счётчики без перезагрузки ленты. */
      onCardAdded(card) {
        this.bumpCardCounts(card.badge_id, { users: 1 });
      },

      onCardReceived(card) {
        this.bumpCardCounts(card.badge_id, { received: 1 });
      },

      onCardUnreceived(card) {
        this.bumpCardCounts(card.badge_id, { received: -1 });
      },

      onCardRemoved(card) {
        this.bumpCardCounts(card.badge_id, {
          users: -1,
          received: card.received ? -1 : 0
        });
      },

      bumpCardCounts(badgeId, deltas) {
        var item = this.badges.find(function (b) {
          return String(b.id) === String(badgeId);
        });
        if (!item) return;

        item.users_count = Math.max(
          0,
          (item.users_count || 0) + (deltas.users || 0)
        );
        item.received_count = Math.max(
          0,
          (item.received_count || 0) + (deltas.received || 0)
        );
      },

      async reloadCards() {
        await this.refreshMine();
      }
    };

    /* Общие методы карточки: клик, long-press, добавление/удаление. */
    return Object.assign(component, window.badgeCardMixin);
  });
});
