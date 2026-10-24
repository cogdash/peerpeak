/* ============================================================
   BADGE — Alpine-компонент страницы отдельного значка
   ============================================================ */
document.addEventListener('alpine:init', function () {
  var ME_URL = '/api/me';
  var BADGES_URL = '/api/badges';
  var USER_BADGES_URL = '/api/user-badges';
  var LONGPRESS_MS = 1200;

  var EMOJI_CHOICES = [
    '🏆', '💰', '🎖️', '⭐', '🔥', '💪', '🚀', '🧠',
    '🎯', '📚', '💡', '❤️', '😎', '🤝', '😈', '⚡',
    '💀', '🤡', '🎓', '🥴', '💤', '😢', '🧳', '🍔'
  ];

  function getBadgeIdFromPath() {
    var match = window.location.pathname.match(/^\/badge\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  function formatDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }

  function formatDateFull(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    try { return d.toLocaleString('ru-RU'); } catch (e) { return ''; }
  }

  Alpine.data('badgePage', function () {
    return {
      loading: true,
      error: '',
      badge: null,
      me: null,
      /* Мой user-badge для этого значка, если он уже есть на моей странице. */
      myBadge: null,

      /* --- Модалка иконки --- */
      emojiChoices: EMOJI_CHOICES,
      emojiModal: { open: false },

      /* --- Long-press → получение --- */
      pressing: false,
      pressTimer: null,

      init() {
        this._onPointerUp = this.cancelPress.bind(this);
        document.addEventListener('pointerup', this._onPointerUp);
        document.addEventListener('pointercancel', this._onPointerUp);
        window.addEventListener('blur', this._onPointerUp);
        document.addEventListener('scroll', this._onPointerUp, true);

        this.load();
      },

      destroy() {
        document.removeEventListener('pointerup', this._onPointerUp);
        document.removeEventListener('pointercancel', this._onPointerUp);
        window.removeEventListener('blur', this._onPointerUp);
        document.removeEventListener('scroll', this._onPointerUp, true);
        clearTimeout(this.pressTimer);
      },

      /* ======================================================
         ВЫЧИСЛЯЕМЫЕ ЗНАЧЕНИЯ
         ====================================================== */
      get canPress() {
        if (!this.me || !this.badge) return false;
        return this.myBadge ? !this.myBadge.received : true;
      },

      get badgeClass() {
        if (!this.badge) return [];
        return [
          this.badge.polarity === 'positive' ? 'pos' : 'neg',
          this.myBadge && !this.myBadge.received ? 'unreceived' : '',
          this.canPress ? 'can-press' : '',
          this.pressing ? 'pressing' : ''
        ].filter(Boolean);
      },

      get kindLabel() {
        if (!this.badge) return '';
        return this.badge.polarity === 'negative' ? 'Анти-достижение' : 'Достижение';
      },

      get isCreator() {
        if (!this.me || !this.badge) return false;
        return String(this.badge.creator_id) === String(this.me.id);
      },

      receivedDate(iso) {
        return formatDate(iso);
      },

      receivedDateFull(iso) {
        return formatDateFull(iso);
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

      async loadMyBadge() {
        var r = await apiFetch(BADGES_URL);
        if (r.ok && Array.isArray(r.data)) this.setMyBadgeFromList(r.data);
      },

      /* ======================================================
         ДЕЙСТВИЯ СО СТАТУСОМ НА МОЕЙ СТРАНИЦЕ
         ====================================================== */
      async addBadge() {
        if (!this.badge || this.myBadge) return null;

        var r = await apiFetch(BADGES_URL, {
          method: 'POST',
          body: JSON.stringify({ title: this.badge.title })
        });
        if (r.status === 401) { window.location.assign('/auth'); return null; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return null;
        }

        this.myBadge = r.data;
        this.$store.toast.show('Значок добавлен на вашу страницу');
        return r.data;
      },

      async receiveBadge() {
        if (!this.myBadge) return;

        var r = await apiFetch(USER_BADGES_URL + '/' + this.myBadge.id + '/receive', {
          method: 'POST'
        });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }

        this.myBadge = r.data;
        this.$store.toast.show('Значок получен! 🎉');
      },

      async unreceiveBadge() {
        if (!this.myBadge) return;

        var r = await apiFetch(USER_BADGES_URL + '/' + this.myBadge.id + '/unreceive', {
          method: 'POST'
        });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }

        this.myBadge = r.data;
        this.$store.toast.show('Получение отменено');
      },

      async removeBadge() {
        if (!this.myBadge) return;

        var r = await apiFetch(USER_BADGES_URL + '/' + this.myBadge.id, {
          method: 'DELETE'
        });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok && r.status !== 204) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }

        this.myBadge = null;
        this.$store.toast.show('Значок убран со страницы');
      },

      /* ======================================================
         LONG-PRESS → ПОЛУЧИТЬ ЗНАЧОК
         ====================================================== */
      startPress(e) {
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        if (e.target.closest('button') || e.target.closest('a')) return;
        if (!this.canPress) return;

        this.cancelPress();
        this.pressing = true;
        this.pressTimer = setTimeout(function () {
          this.completePress();
        }.bind(this), LONGPRESS_MS);
      },

      cancelPress() {
        if (this.pressTimer) {
          clearTimeout(this.pressTimer);
          this.pressTimer = null;
        }
        this.pressing = false;
      },

      async completePress() {
        this.pressTimer = null;
        this.pressing = false;

        if (this.myBadge) {
          if (!this.myBadge.received) await this.receiveBadge();
          return;
        }

        var created = await this.addBadge();
        if (created && created.id != null) {
          await apiFetch(USER_BADGES_URL + '/' + created.id + '/receive', {
            method: 'POST'
          });
          await this.loadMyBadge();
        }
      },

      /* ======================================================
         СМЕНА ИКОНКИ
         ====================================================== */
      openEmojiModal() {
        if (!this.isCreator) return;
        this.emojiModal = { open: true };
      },

      closeEmojiModal() {
        this.emojiModal = { open: false };
      },

      isActiveEmoji(emoji) {
        return !!(this.badge && this.badge.emoji === emoji);
      },

      async pickEmoji(emoji) {
        this.closeEmojiModal();
        await this.saveEmoji(emoji);
      },

      async saveEmoji(emoji) {
        if (!this.badge) return;

        var r = await apiFetch(BADGES_URL + '/' + this.badge.id, {
          method: 'PATCH',
          body: JSON.stringify({ emoji: emoji })
        });

        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }

        this.badge.emoji = r.data.emoji;
        this.$store.toast.show('Иконка обновлена');
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

        window.location.assign('/');
      }
    };
  });
});
