/* ============================================================
   ОБЩИЕ УТИЛИТЫ ДЛЯ ОБЕИХ СТРАНИЦ
   ============================================================ */
(function () {
  'use strict';

  /* Человекочитаемые названия полей для сообщений валидации */
  var FIELD_LABELS = {
    username:  'юзернейм',
    full_name: 'полное имя',
    password:  'пароль',
    bio:       'о себе',
    title:     'название'
  };

  /* Экранирует HTML-спецсимволы. */
  window.escapeHtml = function (text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  /* Превращает обычный текст в безопасный HTML со ссылками.
     Ссылки ищет linkify (подключён только на странице профиля),
     он же экранирует HTML. Если библиотеки нет — отдаём простой текст. */
  window.renderBioHtml = function (text) {
    if (!text) return '';

    if (typeof linkifyStr === 'function') {
      return linkifyStr(text, {
        defaultProtocol: 'https',
        target: '_blank',
        rel: 'noopener noreferrer nofollow'
      });
    }

    return window.escapeHtml(text);
  };

  /* ============================================================
     ОБЩАЯ КАРТОЧКА ЗНАЧКА
     Один набор методов для профиля, страницы значка и ленты.
     Карточка получает нормализованный объект:
       { key, badge_id, user_badge_id, title, emoji, polarity,
         added, received, editable, creator_username, received_at,
         href, show_status, received_count, users_count }
     added/received описывают состояние ТЕКУЩЕГО пользователя,
     поэтому карточка одинаково работает и на своём, и на чужом
     профиле, и в ленте.
     ============================================================ */
  var BADGES_URL = '/api/badges';
  var USER_BADGES_URL = '/api/user-badges';
  var LONGPRESS_MS = 1200;
  /* Дольше короткого тапа — значит пользователь начал зажатие. */
  var HOLD_MS = 300;

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

  /* Русское склонение: 1 пользователь, 2 пользователя, 5 пользователей. */
  function pluralRu(n, one, few, many) {
    var abs = Math.abs(n) % 100;
    var last = abs % 10;
    if (abs > 10 && abs < 20) return many;
    if (last > 1 && last < 5) return few;
    if (last === 1) return one;
    return many;
  }

  window.badgeCardMixin = {
    /* --- Состояние long-press и текущего действия --- */
    pressingKey: null,
    pressTimer: null,
    pressStartedAt: null,
    holdCanceledClick: false,
    cardBusyKey: null,

    bindCardPress() {
      this._onPointerUp = this.cancelPress.bind(this);
      document.addEventListener('pointerup', this._onPointerUp);
      document.addEventListener('pointercancel', this._onPointerUp);
      window.addEventListener('blur', this._onPointerUp);
      document.addEventListener('scroll', this._onPointerUp, true);
    },

    unbindCardPress() {
      document.removeEventListener('pointerup', this._onPointerUp);
      document.removeEventListener('pointercancel', this._onPointerUp);
      window.removeEventListener('blur', this._onPointerUp);
      document.removeEventListener('scroll', this._onPointerUp, true);
      clearTimeout(this.pressTimer);
    },

    /* ======================================================
       ОТОБРАЖЕНИЕ
       ====================================================== */
    cardClass(card) {
      return [
        card.polarity === 'positive' ? 'pos' : 'neg',
        card.added && !card.received ? 'unreceived' : '',
        card.href ? 'clickable' : '',
        this.pressingKey === card.key ? 'pressing' : ''
      ].filter(Boolean).join(' ');
    },

    kindLabel(card) {
      return card.polarity === 'negative' ? 'Анти-достижение' : 'Достижение';
    },

    showCreator(card) {
      return !!card.creator_username &&
        (!this.me || card.creator_username !== this.me.username);
    },

    creatorHref(card) {
      return '/@' + encodeURIComponent(card.creator_username);
    },

    cardDate(iso) {
      return formatDate(iso);
    },

    cardDateFull(iso) {
      return formatDateFull(iso);
    },

    cardStatus(card) {
      if (!card.added) return '';
      return card.received ? '✅' : '📎';
    },

    cardStatusTitle(card) {
      return card.received ? 'У вас получен' : 'У вас на странице';
    },

    /* Счётчик на карточке: получили / добавили. */
    cardUsersText(card) {
      return (card.received_count || 0) + '/' + (card.users_count || 0) + ' 👥';
    },

    cardUsersTitle(card) {
      var received = card.received_count || 0;
      var total = card.users_count || 0;
      return 'Получен у ' + received + ' из ' + total + ' ' +
        pluralRu(total, 'пользователя', 'пользователей', 'пользователей');
    },

    canEditIcon(card) {
      return !!card.editable;
    },

    /* ======================================================
       КЛИК И ДОЛГОЕ ЗАЖАТИЕ
       ====================================================== */
    openBadgeFromCard(e, card) {
      if (this.holdCanceledClick) return;
      if (e.target.closest('button') || e.target.closest('a')) return;
      if (!card.href) return;
      window.location.assign(card.href);
    },

    startPress(e, card) {
      if (!this.me || this.cardBusyKey) return;
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (e.target.closest('button') || e.target.closest('a')) return;

      this.cancelPress();
      this.holdCanceledClick = false;
      this.pressStartedAt = Date.now();

      /* Уже получен — зажатие не должно открывать страницу. */
      if (card.received) return;

      this.pressingKey = card.key;
      this.pressTimer = setTimeout(function () {
        this.completePress(card);
      }.bind(this), LONGPRESS_MS);
    },

    cancelPress() {
      if (this.pressTimer) {
        clearTimeout(this.pressTimer);
        this.pressTimer = null;
      }
      this.pressingKey = null;

      if (this.pressStartedAt !== null) {
        var held = Date.now() - this.pressStartedAt;
        this.pressStartedAt = null;
        if (held >= HOLD_MS) this.holdCanceledClick = true;
      }
    },

    completePress(card) {
      this.pressTimer = null;
      this.pressingKey = null;
      this.pressStartedAt = null;
      /* Браузер пришлёт click после pointerup — не открываем страницу. */
      this.holdCanceledClick = true;

      if (card.received) return;
      if (card.added) {
        this.receiveCard(card);
      } else {
        this.addAndReceiveCard(card);
      }
    },

    /* ======================================================
       ДЕЙСТВИЯ
       ====================================================== */
    async addCard(card) {
      await this._addCard(card, false);
    },

    async addAndReceiveCard(card) {
      await this._addCard(card, true);
    },

    async _addCard(card, receive) {
      if (!this.me || this.cardBusyKey || card.added) return;

      this.cardBusyKey = card.key;
      try {
        var r = await apiFetch(BADGES_URL, {
          method: 'POST',
          body: JSON.stringify({ title: card.title })
        });

        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }

        if (this.onCardAdded) this.onCardAdded(card);

        var newId = (r.data && r.data.id != null) ? r.data.id : null;
        if (!receive || !newId) {
          this.$store.toast.show('Значок добавлен на вашу страницу');
          await this.reloadCards();
          return;
        }

        var r2 = await apiFetch(USER_BADGES_URL + '/' + newId + '/receive', {
          method: 'POST'
        });
        if (r2.ok && this.onCardReceived) this.onCardReceived(card);
        this.$store.toast.show(r2.ok
          ? 'Значок добавлен и получен! 🎉'
          : 'Значок добавлен на вашу страницу');

        await this.reloadCards();
      } catch (e) {
        this.$store.toast.show('Нет связи с сервером');
      } finally {
        this.cardBusyKey = null;
      }
    },

    async receiveCard(card) {
      if (!card.user_badge_id || this.cardBusyKey) return;

      this.cardBusyKey = card.key;
      try {
        var r = await apiFetch(
          USER_BADGES_URL + '/' + card.user_badge_id + '/receive',
          { method: 'POST' }
        );
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }
        this.$store.toast.show('Значок получен! 🎉');
        if (this.onCardReceived) this.onCardReceived(card);
        await this.reloadCards();
      } catch (e) {
        this.$store.toast.show('Нет связи с сервером');
      } finally {
        this.cardBusyKey = null;
      }
    },

    async unreceiveCard(card) {
      if (!card.user_badge_id || this.cardBusyKey) return;

      this.cardBusyKey = card.key;
      try {
        var r = await apiFetch(
          USER_BADGES_URL + '/' + card.user_badge_id + '/unreceive',
          { method: 'POST' }
        );
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }
        this.$store.toast.show('Получение отменено');
        if (this.onCardUnreceived) this.onCardUnreceived(card);
        await this.reloadCards();
      } catch (e) {
        this.$store.toast.show('Нет связи с сервером');
      } finally {
        this.cardBusyKey = null;
      }
    },

    async removeCard(card) {
      if (!card.user_badge_id || this.cardBusyKey) return;

      this.cardBusyKey = card.key;
      try {
        var r = await apiFetch(
          USER_BADGES_URL + '/' + card.user_badge_id,
          { method: 'DELETE' }
        );
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok && r.status !== 204) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }
        if (this.onCardRemoved) this.onCardRemoved(card);
        this.$store.toast.show('Значок убран со страницы');
        await this.reloadCards();
      } catch (e) {
        this.$store.toast.show('Нет связи с сервером');
      } finally {
        this.cardBusyKey = null;
      }
    },

    /* ======================================================
       ИКОНКА
       ====================================================== */
    openEmojiModal(card) {
      if (!this.canEditIcon(card)) return;
      this.emojiModal = { open: true, badge: card };
    },

    closeEmojiModal() {
      this.emojiModal = { open: false, badge: null };
    },

    isActiveEmoji(emoji) {
      return !!(this.emojiModal.badge && this.emojiModal.badge.emoji === emoji);
    },

    async pickEmoji(emoji) {
      var card = this.emojiModal.badge;
      this.closeEmojiModal();
      if (!card) return;

      var r = await apiFetch(BADGES_URL + '/' + encodeURIComponent(card.badge_id), {
        method: 'PATCH',
        body: JSON.stringify({ emoji: emoji })
      });

      if (r.status === 401) { window.location.assign('/auth'); return; }
      if (!r.ok) {
        this.$store.toast.show(extractErrorMessage(r.data, r.status));
        return;
      }

      this.$store.toast.show('Иконка обновлена');
      await this.reloadCards();
    }
  };

  /* Превращает ответ FastAPI в понятный текст.
     - HTTPException: { detail: "строка" }
     - Ошибка валидации (422): { detail: [ { loc, msg, ... } ] } */
  window.extractErrorMessage = function (data, status) {
    if (data && typeof data.detail === 'string') {
      return data.detail;
    }

    if (data && Array.isArray(data.detail) && data.detail.length) {
      return data.detail.map(function (item) {
        var field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : '';
        var label = FIELD_LABELS[field] || field;
        var msg = item.msg || 'неверное значение';

        if (item.type === 'string_too_short') {
          var min = item.ctx && item.ctx.min_length;
          return 'Поле «' + label + '»: минимум ' + min + ' симв.';
        }
        if (item.type === 'string_too_long') {
          var max = item.ctx && item.ctx.max_length;
          return 'Поле «' + label + '»: максимум ' + max + ' симв.';
        }
        if (item.type === 'missing') {
          return 'Заполни поле «' + label + '»';
        }
        return label ? ('Поле «' + label + '»: ' + msg) : msg;
      }).join('; ');
    }

    if (data && typeof data.reason === 'string') {
      return data.reason;
    }

    return 'Что-то пошло не так (' + status + ')';
  };

  /* fetch + JSON с единым форматом ответа. */
  window.apiFetch = async function (url, options) {
    options = options || {};
    options.headers = Object.assign(
      { 'Accept': 'application/json' },
      options.headers || {}
    );
    if (options.body && !options.headers['Content-Type']) {
      options.headers['Content-Type'] = 'application/json';
    }

    var res = await fetch(url, options);
    var data = null;
    if (res.status !== 204) {
      try { data = await res.json(); } catch (e) { data = null; }
    }
    return { ok: res.ok, status: res.status, data: data };
  };

  /* ============================================================
     TOAST — общий Alpine-store
     ============================================================ */
  document.addEventListener('alpine:init', function () {
    Alpine.store('toast', {
      message: '',
      visible: false,
      timer: null,

      show: function (msg, ms) {
        this.message = msg;
        this.visible = true;
        clearTimeout(this.timer);
        this.timer = setTimeout(function () {
          this.visible = false;
        }.bind(this), ms || 2400);
      }
    });
  });
})();
