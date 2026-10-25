/* ============================================================
   BADGE — Alpine-компонент страницы отдельного значка
   ============================================================ */
document.addEventListener('alpine:init', function () {
  var ME_URL = '/api/me';
  var BADGES_URL = '/api/badges';

  var EMOJI_CHOICES = [
    '🏆', '💰', '🎖️', '⭐', '🔥', '💪', '🚀', '🧠',
    '🎯', '📚', '💡', '❤️', '😎', '🤝', '😈', '⚡',
    '💀', '🤡', '🎓', '🥴', '💤', '😢', '🧳', '🍔'
  ];

  function getBadgeIdFromPath() {
    var match = window.location.pathname.match(/^\/badge\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  Alpine.data('badgePage', function () {
    var component = {
      loading: true,
      error: '',
      badge: null,
      me: null,
      /* Мой user-badge для этого значка, если он уже есть на моей странице. */
      myBadge: null,

      /* --- Модалка иконки --- */
      emojiChoices: EMOJI_CHOICES,
      emojiModal: { open: false, badge: null },

      init() {
        this.bindCardPress();
        this.load();
      },

      destroy() {
        this.unbindCardPress();
      },

      /* ======================================================
         ВЫЧИСЛЯЕМЫЕ ЗНАЧЕНИЯ
         ====================================================== */
      get isCreator() {
        if (!this.me || !this.badge) return false;
        return String(this.badge.creator_id) === String(this.me.id);
      },

      /* Та же форма карточки, что на профиле и в ленте. */
      get card() {
        if (!this.badge) return null;

        var mine = this.myBadge;
        return {
          key: String(this.badge.id),
          badge_id: this.badge.id,
          user_badge_id: mine ? mine.id : null,
          title: this.badge.title,
          emoji: this.badge.emoji,
          polarity: this.badge.polarity,
          added: !!mine,
          received: !!(mine && mine.received),
          editable: this.isCreator,
          creator_username: this.badge.creator_username || '',
          received_at: mine ? mine.received_at : null,
          href: null,
          show_status: true,
          extra_text: '',
          extra_title: ''
        };
      },

      /* ======================================================
         ЗАГРУЗКА
         ====================================================== */
      async load() {
        var badgeId = getBadgeIdFromPath();
        if (!badgeId) {
          this.loading = false;
          this.error = 'Значок не найден.';
          return;
        }

        try {
          /* /api/me и /api/badges нужны для статуса значка на моей странице.
             Сама страница доступна и без входа. */
          var results = await Promise.all([
            apiFetch(BADGES_URL + '/' + encodeURIComponent(badgeId)),
            apiFetch(ME_URL),
            apiFetch(BADGES_URL)
          ]);
          var badgeRes = results[0];
          var meRes = results[1];
          var myBadgesRes = results[2];

          if (meRes.ok) this.me = meRes.data;

          if (badgeRes.status === 404) {
            this.error = 'Значок не найден.';
            return;
          }
          if (!badgeRes.ok) {
            this.error = 'Не удалось загрузить значок.';
            return;
          }

          this.badge = badgeRes.data;
          if (myBadgesRes.ok && Array.isArray(myBadgesRes.data)) {
            this.setMyBadgeFromList(myBadgesRes.data);
          }
          document.title = 'Peerpeak: ' + this.badge.title;
        } catch (e) {
          this.error = 'Нет связи с сервером.';
        } finally {
          this.loading = false;
        }
      },

      setMyBadgeFromList(list) {
        var badgeId = this.badge ? String(this.badge.id) : null;
        var found = list.find(function (item) {
          return item && String(item.badge_id) === badgeId;
        });
        this.myBadge = found || null;
      },

      /* Перезагрузка состояния общей карточки после действия. */
      async reloadCards() {
        if (!this.badge) return;

        var badgeId = encodeURIComponent(this.badge.id);
        var results = await Promise.all([
          apiFetch(BADGES_URL + '/' + badgeId),
          apiFetch(ME_URL),
          apiFetch(BADGES_URL)
        ]);

        if (results[0].ok) this.badge = results[0].data;
        if (results[1].ok) this.me = results[1].data;
        if (results[2].ok && Array.isArray(results[2].data)) {
          this.setMyBadgeFromList(results[2].data);
        }
      },

      /* ======================================================
         ПОДЕЛИТЬСЯ
         ====================================================== */
      shareBadge() {
        if (!this.badge) return;

        var url = window.location.origin + '/badge/' + encodeURIComponent(this.badge.id);
        var title = 'Значок «' + this.badge.title + '» на Peerpeak';
        var self = this;

        if (navigator.share) {
          navigator.share({
            title: title,
            text: 'Посмотри этот значок в Peerpeak!',
            url: url
          }).catch(function (err) {
            if (err && err.name !== 'AbortError') self.copyToClipboard(url);
          });
        } else {
          this.copyToClipboard(url);
        }
      },

      copyToClipboard(text) {
        var textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand('copy');
          this.$store.toast.show('Ссылка скопирована');
        } catch (e) {
          this.$store.toast.show('Не удалось скопировать ссылку');
        }
        document.body.removeChild(textarea);
      },

      /* ======================================================
         НАВИГАЦИЯ
         ====================================================== */
      goBack() {
        try {
          if (document.referrer) {
            var ref = new URL(document.referrer);
            if (ref.origin === window.location.origin) {
              window.history.back();
              return;
            }
          }
        } catch (e) { /* некорректный referrer — идём на главную */ }

        window.location.assign('/feed');
      }
    };

    /* Общие методы карточки: клик, long-press, добавление/удаление, иконка. */
    return Object.assign(component, window.badgeCardMixin);
  });
});
