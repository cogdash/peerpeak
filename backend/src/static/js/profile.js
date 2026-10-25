/* ============================================================
   PROFILE — Alpine-компонент страницы профиля
   ============================================================ */
document.addEventListener('alpine:init', function () {
  var LOOKUP_URL      = '/api/badge/lookup';
  var BADGES_URL      = '/api/badges';
  var CATALOG_URL     = '/api/badges/catalog';
  var USERS_URL       = '/api/users';
  var ME_URL          = '/api/me';
  var SIGNOUT_URL     = '/api/signout';

  var DEFAULT_PLACEHOLDER = 'выучил новый язык';

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
    var component = {
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

      /* --- Подписки --- */
      followLoading: false,
      followModalSeq: 0,
      followModal: { open: false, mode: 'followers', loading: false, users: [], error: '' },

      /* --- Анимация маркера баланса --- */
      balancePct: '0%',

      init() {
        this.viewedUsername = getUsernameFromPath();
        this.bindCardPress();
        this.load();
      },

      destroy() {
        this.unbindCardPress();
        clearTimeout(this.detectTimer);
      },

      /* ======================================================
         ВЫЧИСЛЯЕМЫЕ ЗНАЧЕНИЯ
         ====================================================== */
      get bioHtml() {
        return this.profile && this.profile.bio
          ? renderBioHtml(this.profile.bio)
          : '';
      },

      get followersText() {
        var n = this.profile ? (this.profile.followers_count || 0) : 0;
        return n + ' ' + this.plural(n, 'подписчик', 'подписчика', 'подписчиков');
      },

      get followingText() {
        var n = this.profile ? (this.profile.following_count || 0) : 0;
        return n + ' ' + this.plural(n, 'подписка', 'подписки', 'подписок');
      },

      get followModalTitle() {
        return this.followModal.mode === 'followers' ? 'Подписчики' : 'Подписки';
      },

      get followEmptyText() {
        if (this.followModal.error) return this.followModal.error;
        return this.followModal.mode === 'followers'
          ? 'Пока нет подписчиков.'
          : 'Пока нет подписок.';
      },

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

      get filteredCards() {
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

        return items.map(this.toCard, this);
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

      /* Приводит значок профиля к общему виду карточки. */
      toCard(b) {
        var mine = this.myBadge(b);
        var own = this.isOwnProfile;

        return {
          key: String(b.id),
          badge_id: b.badge_id,
          user_badge_id: own ? b.id : (mine ? mine.id : null),
          title: b.title,
          emoji: b.emoji,
          polarity: b.polarity,
          added: own ? true : !!mine,
          received: own ? !!b.received : !!(mine && mine.received),
          editable: own && !!b.is_creator,
          creator_username: b.creator_username,
          received_at: b.received ? b.received_at : null,
          href: '/badge/' + encodeURIComponent(b.badge_id),
          show_status: !own,
          extra_text: '',
          extra_title: ''
        };
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
          /* Свой профиль: тоже тянем публичные данные, чтобы получить счётчики. */
          var own = await this.loadViewedUser();
          this.profile = own || this.me;
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
          if (this.isOwnProfile) {
            /* Сохраняем счётчики подписок, которых нет в ответе /api/me. */
            this.profile = Object.assign({}, this.profile, r.data);
          }

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
         ПОДПИСКИ
         ====================================================== */
      plural(n, one, few, many) {
        var abs = Math.abs(n) % 100;
        var last = abs % 10;
        if (abs > 10 && abs < 20) return many;
        if (last > 1 && last < 5) return few;
        if (last === 1) return one;
        return many;
      },

      async toggleFollow() {
        if (!this.profile || this.isOwnProfile || this.followLoading) return;

        var following = !!this.profile.is_following;
        this.followLoading = true;

        try {
          var r = await apiFetch(
            USERS_URL + '/' + encodeURIComponent(this.profile.username) + '/follow',
            { method: following ? 'DELETE' : 'POST' }
          );

          if (r.status === 401) { window.location.assign('/auth'); return; }
          if (!r.ok) {
            this.$store.toast.show(extractErrorMessage(r.data, r.status));
            return;
          }

          this.profile.is_following = r.data.following;
          this.profile.followers_count = r.data.followers_count;
          this.$store.toast.show(
            r.data.following
              ? 'Подписались на @' + this.profile.username
              : 'Отписались от @' + this.profile.username
          );
        } catch (e) {
          this.$store.toast.show('Нет связи с сервером');
        } finally {
          this.followLoading = false;
        }
      },

      isMe(u) {
        return !!(this.me && u && u.username === this.me.username);
      },

      async toggleFollowUser(u) {
        if (!u || u.busy || this.isMe(u)) return;

        var wasFollowing = !!u.is_following;
        u.busy = true;

        try {
          var r = await apiFetch(
            USERS_URL + '/' + encodeURIComponent(u.username) + '/follow',
            { method: wasFollowing ? 'DELETE' : 'POST' }
          );

          if (r.status === 401) { window.location.assign('/auth'); return; }
          if (!r.ok) {
            this.$store.toast.show(extractErrorMessage(r.data, r.status));
            return;
          }

          u.is_following = r.data.following;

          /* Если открыт профиль этого же пользователя — синхронизируем шапку. */
          if (this.profile && this.profile.username === u.username) {
            this.profile.is_following = r.data.following;
            this.profile.followers_count = r.data.followers_count;
          }

          /* Мои подписки меняются при любом действии из модалки. */
          if (this.isOwnProfile) {
            var delta = (r.data.following ? 1 : 0) - (wasFollowing ? 1 : 0);
            this.profile.following_count =
              Math.max(0, (this.profile.following_count || 0) + delta);
          }
        } catch (e) {
          this.$store.toast.show('Нет связи с сервером');
        } finally {
          u.busy = false;
        }
      },

      async openFollowModal(mode) {
        if (!this.profile) return;

        this.followModal = { open: true, mode: mode, loading: true, users: [], error: '' };

        var seq = ++this.followModalSeq;

        try {
          var r = await apiFetch(
            USERS_URL + '/' + encodeURIComponent(this.profile.username) + '/' + mode
          );
          if (seq !== this.followModalSeq) return;

          if (r.status === 401) { window.location.assign('/auth'); return; }
          if (!r.ok) {
            this.followModal.error = 'Не удалось загрузить список';
            return;
          }

          this.followModal.users = (Array.isArray(r.data) ? r.data : []).map(function (item) {
            return Object.assign({}, item, { busy: false });
          });
        } catch (e) {
          if (seq === this.followModalSeq) this.followModal.error = 'Нет связи с сервером';
        } finally {
          if (seq === this.followModalSeq) this.followModal.loading = false;
        }
      },

      closeFollowModal() {
        this.followModalSeq++;
        this.followModal = { open: false, mode: 'followers', loading: false, users: [], error: '' };
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
      },

      /* Общая карточка значка перезагружает данные профиля. */
      async reloadCards() {
        await this.loadBadges();
      }
    };

    /* Методы карточки (клик, long-press, добавление/удаление, иконка)
       общие для профиля, страницы значка и ленты. */
    return Object.assign(component, window.badgeCardMixin);
  });
});
