/* ============================================================
   PROFILE — Alpine-компонент страницы профиля
   ============================================================ */
document.addEventListener('alpine:init', function () {
  var LOOKUP_URL      = '/api/badge/lookup';
  var BADGES_URL      = '/api/badges';
  var CATALOG_URL     = '/api/badges/catalog';
  var USER_BADGES_URL = '/api/user-badges';
  var ME_URL          = '/api/me';
  var SIGNOUT_URL     = '/api/signout';

  var DEFAULT_PLACEHOLDER = 'выучил новый язык';
  var LONGPRESS_MS = 1200;
  /* Дольше короткого тапа — значит пользователь начал зажатие. */
  var HOLD_MS = 300;

  var EMOJI_CHOICES = [
    '🏆', '💰', '🎖️', '⭐', '🔥', '💪', '🚀', '🧠',
    '🎯', '📚', '💡', '❤️', '😎', '🤝', '😈', '⚡',
    '💀', '🤡', '🎓', '🥴', '💤', '😢', '🧳', '🍔'
  ];

  /* ==========================================================
     БАЛАНС ПРОФИЛЯ
     ========================================================== */
  var BALANCE_VERDICTS = {
    pos: { icon: '🎭', text: 'витрина', hint: 'Одни достижения. Такое вообще бывает?' },
    bal: { icon: '⚖️', text: 'баланс',  hint: 'Здоровое соотношение: и победы, и провалы.' },
    neg: { icon: '🌧️', text: 'траур',   hint: 'Слишком много провалов. Может, стоит вспомнить и победы?' }
  };

  /* Границы зон по доле достижений p/(p+n):
     < 0.55       → «мрачновато»
     0.55 .. 0.85 → «баланс»   (идеал ≈ 3:1 = 0.75)
     > 0.85       → «витрина»  */
  var BALANCE_MIN_TOTAL = 5;
  var BALANCE_LOW       = 0.55;
  var BALANCE_HIGH      = 0.85;

  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

  function getUsernameFromPath() {
    var match = window.location.pathname.match(/^\/@([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  Alpine.data('profilePage', function () {
    return {
      /* --- Состояние загрузки --- */
      me: null,
      profile: null,
      badges: [],
      catalog: [],
      /* badge_id -> мой user-badge (если он у меня есть) */
      myBadgesByBadgeId: {},
      viewedUsername: null,
      isOwnProfile: false,

      /* --- Фильтры --- */
      filter: 'all',
      showReceivedOnly: false,
      showSharedOnly: false,

      /* --- Добавление значка --- */
      newTitle: '',
      titleInvalid: false,
      adding: false,
      catalogPlaceholder: DEFAULT_PLACEHOLDER,

      /* --- Определение полярности --- */
      detect: { state: 'idle', polarity: 'positive', inCatalog: false },
      detectTimer: null,
      detectSeq: 0,

      /* --- Модалка иконки --- */
      emojiChoices: EMOJI_CHOICES,
      emojiModal: { open: false, badge: null },

      /* --- Модалка редактирования профиля --- */
      editModal: { open: false, full_name: '', username: '', bio: '', saving: false },

      /* --- Long-press --- */
      pressingId: null,
      pressTimer: null,
      pressStartedAt: null,
      /* Зажатие не должно открывать страницу значка. */
      holdCanceledClick: false,

      /* --- Анимация маркера баланса --- */
      balancePct: '0%',

      init() {
        this.viewedUsername = getUsernameFromPath();

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
        clearTimeout(this.detectTimer);
      },

      /* ======================================================
         ВЫЧИСЛЯЕМЫЕ ЗНАЧЕНИЯ
         ====================================================== */
      get joinedText() {
        if (!this.profile || !this.profile.created_at) return '';
        var d = new Date(this.profile.created_at);
        if (isNaN(d.getTime())) return '';
        return 'В Peerpeak с ' + d.getDate() + ' ' +
          MONTHS[d.getMonth()] + ' ' + d.getFullYear() + ' г.';
      },

      get balance() {
        var p = 0, n = 0;
        (this.badges || []).forEach(function (b) {
          if (!b.received) return; /* учитываем только полученные */
          if (b.polarity === 'positive') p++;
          else n++;
        });

        var total = p + n;
        if (total < BALANCE_MIN_TOTAL) return null;

        var score = p / total;
        var zone;
        if (score > BALANCE_HIGH)     zone = 'pos';
        else if (score < BALANCE_LOW) zone = 'neg';
        else                          zone = 'bal';

        var verdict = BALANCE_VERDICTS[zone];

        return {
          zone: zone,
          icon: verdict.icon,
          text: verdict.text,
          positives: p,
          negatives: n,
          total: total,
          pct: (score * 100).toFixed(1) + '%',
          tooltip: verdict.hint +
            '\nПолученных достижений: ' + p +
            '\nПолученных антидостижений: ' + n +
            '\nИдеал — около 3:1 (75%)'
        };
      },

      get filteredBadges() {
        var items = this.filter === 'all'
          ? this.badges
          : this.badges.filter(function (b) { return b.polarity === this.filter; }, this);

        if (this.showSharedOnly) {
          /* «Общие» — значки, которые есть и у этого пользователя, и у меня. */
          items = items.filter(function (b) { return !!this.myBadge(b); }, this);
        }
        if (this.showReceivedOnly) {
          items = items.filter(function (b) { return this.isReceivedFor(b); }, this);
        }
        return items;
      },

      get emptyState() {
        if (!this.badges.length) {
          return this.isOwnProfile
            ? { icon: '🏅', text: 'Пока нет ни одного значка. Добавь первый выше!' }
            : { icon: '🏅', text: 'У пользователя пока нет значков.' };
        }
        if (this.showSharedOnly) {
          return { icon: '🤝', text: 'У вас нет общих значков с этим пользователем.' };
        }
        if (this.showReceivedOnly) {
          return { icon: '⏳', text: 'Полученных значков в этой категории пока нет.' };
        }
        return { icon: '🔍', text: 'В этой категории пока ничего нет.' };
      },

      get detectClass() {
        if (this.detect.state !== 'done') return '';
        return this.detect.polarity === 'positive' ? 'pos' : 'neg';
      },

      /* ======================================================
         ХЕЛПЕРЫ ЗНАЧКОВ
         ====================================================== */
      initial(name) {
        return (name || '?').trim().charAt(0).toUpperCase();
      },

      myBadge(b) {
        return this.myBadgesByBadgeId[String(b.badge_id)] || null;
      },

      isReceivedFor(b) {
        if (this.isOwnProfile) return !!b.received;
        var mine = this.myBadge(b);
        return !!(mine && mine.received);
      },

      canPress(b) {
        return this.isOwnProfile ? !b.received : !this.isReceivedFor(b);
      },

      badgeClass(b) {
        return [
          b.polarity === 'positive' ? 'pos' : 'neg',
          b.received ? '' : 'unreceived',
          this.canPress(b) ? 'can-press' : '',
          this.pressingId === b.id ? 'pressing' : ''
        ].filter(Boolean).join(' ');
      },

      kindLabel(b) {
        return b.polarity === 'negative' ? 'Анти-достижение' : 'Достижение';
      },

      showCreator(b) {
        return !!b.creator_username && (!this.me || b.creator_username !== this.me.username);
      },

      creatorHref(b) {
        return '/@' + encodeURIComponent(b.creator_username);
      },

      receivedDate(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
      },

      receivedDateFull(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        try { return d.toLocaleString('ru-RU'); } catch (e) { return ''; }
      },

      /* ======================================================
         ЗАГРУЗКА ДАННЫХ
         ====================================================== */
      async loadMe() {
        var r = await apiFetch(ME_URL);
        if (r.status === 401) { window.location.assign('/auth'); return false; }
        if (!r.ok) { this.$store.toast.show('Не удалось загрузить профиль'); return false; }
        this.me = r.data;
        return true;
      },

      async loadViewedUser() {
        if (!this.viewedUsername) return null;
        var r = await apiFetch('/api/users/@' + encodeURIComponent(this.viewedUsername));
        if (!r.ok) return null;
        return r.data;
      },

      async load() {
        var ok = await this.loadMe();
        if (!ok) return;

        if (this.viewedUsername && this.viewedUsername !== this.me.username) {
          var viewed = await this.loadViewedUser();
          if (viewed) {
            this.profile = viewed;
            this.isOwnProfile = false;
          } else {
            this.profile = this.me;
            this.isOwnProfile = true;
          }
        } else {
          this.profile = this.me;
          this.isOwnProfile = true;
        }

        document.title = 'Peerpeak: @' + this.profile.username;

        await this.loadCatalog();
        this.pickPlaceholder();

        await this.loadBadges();
      },

      async loadBadges() {
        var url = this.isOwnProfile
          ? BADGES_URL
          : '/api/badges/@' + encodeURIComponent(this.viewedUsername);

        var r, myR = null;
        if (this.isOwnProfile) {
          r = await apiFetch(url);
        } else {
          /* Параллельно тянем список владельца и свой — чтобы понять, что у меня уже есть */
          var results = await Promise.all([apiFetch(url), apiFetch(BADGES_URL)]);
          r = results[0];
          myR = results[1];
        }

        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show('Не удалось загрузить значки'); return; }

        var byBadgeId = {};
        if (!this.isOwnProfile && myR && myR.ok && Array.isArray(myR.data)) {
          myR.data.forEach(function (mb) {
            if (!mb || mb.badge_id == null) return;
            var key = String(mb.badge_id);
            var existing = byBadgeId[key];
            /* Если найдётся и полученный, и не полученный вариант — оставляем полученный */
            if (!existing || (mb.received && !existing.received)) {
              byBadgeId[key] = mb;
            }
          });
        }

        this.badges = r.data || [];
        this.myBadgesByBadgeId = byBadgeId;
      },

      async loadCatalog() {
        try {
          var r = await apiFetch(CATALOG_URL);
          if (!r.ok || !Array.isArray(r.data)) return;
          this.catalog = r.data.map(function (item) {
            if (typeof item === 'string') return item;
            return item && item.title ? item.title : '';
          }).filter(Boolean);
        } catch (e) { /* тихо игнорируем */ }
      },

      pickPlaceholder() {
        var titles = (this.catalog || []).filter(function (t) { return t && t.length; });
        if (!titles.length) {
          this.catalogPlaceholder = DEFAULT_PLACEHOLDER;
          return;
        }
        this.catalogPlaceholder = titles[Math.floor(Math.random() * titles.length)];
      },

      /* ======================================================
         ОПРЕДЕЛЕНИЕ ПОЛЯРНОСТИ
         ====================================================== */
      onTitleInput() {
        this.titleInvalid = false;

        clearTimeout(this.detectTimer);
        var text = this.newTitle.trim();

        if (!text) {
          this.detectSeq++;
          this.detect = { state: 'idle', polarity: 'positive', inCatalog: false };
          return;
        }

        this.detectTimer = setTimeout(function () { this.runDetect(text); }.bind(this), 350);
      },

      async runDetect(text) {
        var seq = ++this.detectSeq;
        this.detect = { state: 'loading', polarity: 'positive', inCatalog: false };

        var r = await apiFetch(LOOKUP_URL + '?text=' + encodeURIComponent(text));
        if (seq !== this.detectSeq) return;

        if (!r.ok) {
          this.detect = { state: 'idle', polarity: 'positive', inCatalog: false };
          return;
        }

        this.detect = {
          state: 'done',
          polarity: r.data.polarity,
          inCatalog: !!r.data.badge
        };
      },

      resetDetect() {
        this.detectSeq++;
        this.detect = { state: 'idle', polarity: 'positive', inCatalog: false };
      },

      /* ======================================================
         ДОБАВЛЕНИЕ ЗНАЧКА
         ====================================================== */
      async addBadge() {
        if (!this.isOwnProfile || this.adding) return;

        var title = this.newTitle.trim();
        if (!title) {
          this.titleInvalid = true;
          this.$refs.titleInput && this.$refs.titleInput.focus();
          this.$store.toast.show('Введи название значка');
          return;
        }

        this.titleInvalid = false;
        this.adding = true;

        try {
          var r = await apiFetch(BADGES_URL, {
            method: 'POST',
            body: JSON.stringify({ title: title })
          });

          if (r.status === 401) { window.location.assign('/auth'); return; }
          if (!r.ok) {
            this.$store.toast.show(extractErrorMessage(r.data, r.status));
            return;
          }

          this.newTitle = '';
          this.resetDetect();
          this.$store.toast.show('Значок добавлен');
          await this.loadBadges();
        } catch (e) {
          this.$store.toast.show('Нет связи с сервером');
        } finally {
          this.adding = false;
        }
      },

      /* ======================================================
         ДЕЙСТВИЯ СО ЗНАЧКАМИ
         ====================================================== */
      async receive(id) {
        var r = await apiFetch(USER_BADGES_URL + '/' + id + '/receive', { method: 'POST' });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show(extractErrorMessage(r.data, r.status)); return; }
        this.$store.toast.show('Значок получен! 🎉');
        await this.loadBadges();
      },

      async unreceive(id) {
        var r = await apiFetch(USER_BADGES_URL + '/' + id + '/unreceive', { method: 'POST' });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show(extractErrorMessage(r.data, r.status)); return; }
        this.$store.toast.show('Получение отменено');
        await this.loadBadges();
      },

      async remove(id) {
        var r = await apiFetch(USER_BADGES_URL + '/' + id, { method: 'DELETE' });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok && r.status !== 204) {
          this.$store.toast.show(extractErrorMessage(r.data, r.status));
          return;
        }
        this.$store.toast.show('Значок убран со страницы');
        await this.loadBadges();
      },

      /* Добавить чужой значок к себе.
         Используем тот же эндпоинт, что и на своей странице: POST /api/badges { title }.
         Бэкенд сам сматчит с каталогом и создаст user-badge у текущего пользователя. */
      async add(b) {
        var r = await apiFetch(BADGES_URL, {
          method: 'POST',
          body: JSON.stringify({ title: b.title })
        });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show(extractErrorMessage(r.data, r.status)); return; }
        this.$store.toast.show('Значок добавлен на вашу страницу');
        await this.loadBadges();
      },

      /* Long-press на чужом значке: добавить (если нужно) и сразу засчитать полученным. */
      async addAndReceive(b) {
        var r = await apiFetch(BADGES_URL, {
          method: 'POST',
          body: JSON.stringify({ title: b.title })
        });
        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show(extractErrorMessage(r.data, r.status)); return; }

        /* Ответ POST /api/badges — это созданный user-badge (как в списке на своей странице),
           поэтому его id можно сразу скармливать в /api/user-badges/{id}/receive. */
        var newId = (r.data && r.data.id != null) ? r.data.id : null;
        if (!newId) {
          this.$store.toast.show('Значок добавлен на вашу страницу');
          await this.loadBadges();
          return;
        }

        var r2 = await apiFetch(USER_BADGES_URL + '/' + newId + '/receive', { method: 'POST' });
        this.$store.toast.show(r2.ok
          ? 'Значок добавлен и получен! 🎉'
          : 'Значок добавлен на вашу страницу');

        await this.loadBadges();
      },

      /* Короткий клик по карточке открывает страницу значка. */
      openBadgeFromCard(e, b) {
        if (this.holdCanceledClick) return;
        if (e.target.closest('button') || e.target.closest('a')) return;
        if (!b || b.badge_id == null) return;
        window.location.assign('/badge/' + encodeURIComponent(b.badge_id));
      },

      /* ======================================================
         LONG-PRESS → ПОЛУЧИТЬ ЗНАЧОК
         ====================================================== */
      startPress(e, b) {
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        if (e.target.closest('button') || e.target.closest('a')) return;

        this.cancelPress();
        this.holdCanceledClick = false;
        this.pressStartedAt = Date.now();

        /* Даже если значок уже получен, зажатие не должно открывать страницу. */
        if (this.isReceivedFor(b)) return;

        this.pressingId = b.id;
        this.pressTimer = setTimeout(function () {
          this.completePress(b);
        }.bind(this), LONGPRESS_MS);
      },

      cancelPress() {
        if (this.pressTimer) {
          clearTimeout(this.pressTimer);
          this.pressTimer = null;
        }
        this.pressingId = null;

        if (this.pressStartedAt !== null) {
          var held = Date.now() - this.pressStartedAt;
          this.pressStartedAt = null;
          if (held >= HOLD_MS) this.holdCanceledClick = true;
        }
      },

      completePress(b) {
        this.pressTimer = null;
        this.pressingId = null;
        this.pressStartedAt = null;
        /* Браузер пришлёт click после pointerup — не открываем страницу. */
        this.holdCanceledClick = true;

        if (this.isOwnProfile) {
          if (!b.received) this.receive(b.id);
          return;
        }

        var mine = this.myBadge(b);
        if (mine && !mine.received) {
          this.receive(mine.id);
        } else if (!mine) {
          this.addAndReceive(b);
        }
      },

      /* ======================================================
         МОДАЛКА СМЕНЫ ИКОНКИ
         ====================================================== */
      openEmojiModal(b) {
        if (!this.isOwnProfile || !b.is_creator) return;
        this.emojiModal = { open: true, badge: b };
      },

      closeEmojiModal() {
        this.emojiModal = { open: false, badge: null };
      },

      isActiveEmoji(emoji) {
        return !!(this.emojiModal.badge && this.emojiModal.badge.emoji === emoji);
      },

      async pickEmoji(emoji) {
        var badge = this.emojiModal.badge;
        this.closeEmojiModal();
        if (badge) await this.saveEmoji(badge.badge_id, emoji);
      },

      async saveEmoji(badgeId, emoji) {
        var r = await apiFetch(BADGES_URL + '/' + badgeId, {
          method: 'PATCH',
          body: JSON.stringify({ emoji: emoji })
        });

        if (r.status === 401) { window.location.assign('/auth'); return; }
        if (!r.ok) { this.$store.toast.show(extractErrorMessage(r.data, r.status)); return; }

        this.$store.toast.show('Иконка обновлена');
        await this.loadBadges();
      },

      /* ======================================================
         РЕДАКТИРОВАНИЕ ПРОФИЛЯ
         ====================================================== */
      openEditModal() {
        if (!this.isOwnProfile || !this.me) return;
        this.editModal = {
          open: true,
          full_name: this.me.full_name || '',
          username: this.me.username || '',
          bio: this.me.bio || '',
          saving: false
        };
      },

      closeEditModal() {
        if (this.editModal.saving) return;
        this.editModal.open = false;
      },

      async saveProfile() {
        if (this.editModal.saving) return;

        var fullName = (this.editModal.full_name || '').trim();
        var username = (this.editModal.username || '').trim();
        var bio = (this.editModal.bio || '').trim();

        if (!fullName) {
          this.$store.toast.show('Полное имя не может быть пустым');
          return;
        }
        if (username.length < 3) {
          this.$store.toast.show('Юзернейм должен содержать минимум 3 символа');
          return;
        }

        this.editModal.saving = true;

        try {
          var r = await apiFetch(ME_URL, {
            method: 'PATCH',
            body: JSON.stringify({
              full_name: fullName,
              username: username,
              bio: bio
            })
          });

          if (r.status === 401) { window.location.assign('/auth'); return; }
          if (!r.ok) {
            this.$store.toast.show(extractErrorMessage(r.data, r.status));
            return;
          }

          var newUsername = r.data.username;
          this.me = r.data;
          if (this.isOwnProfile) this.profile = this.me;

          this.editModal.saving = false;
          this.editModal.open = false;

          if (this.isOwnProfile && this.viewedUsername !== newUsername) {
            document.title = 'Peerpeak: @' + newUsername;
            window.location.assign('/@' + encodeURIComponent(newUsername));
            return;
          }

          this.$store.toast.show('Профиль обновлён');
        } catch (e) {
          this.$store.toast.show('Нет связи с сервером');
        } finally {
          this.editModal.saving = false;
        }
      },

      /* ======================================================
         ПОДЕЛИТЬСЯ ПРОФИЛЕМ
         ====================================================== */
      shareProfile() {
        if (!this.profile) return;

        var username = this.profile.username;
        var url = window.location.origin + '/@' + username;
        var self = this;

        if (navigator.share) {
          navigator.share({
            title: 'Профиль @' + username + ' в Peerpeak',
            text: 'Посмотри мой профиль в Peerpeak!',
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
          this.$store.toast.show('Не удалось скопировать. Ссылка: ' + text);
        }
        document.body.removeChild(textarea);
      },

      /* ======================================================
         ПРОЧЕЕ
         ====================================================== */
      async signout() {
        try {
          await apiFetch(SIGNOUT_URL, { method: 'POST' });
        } catch (e) { /* игнорируем */ }
        window.location.assign('/auth');
      }
    };
  });
});
