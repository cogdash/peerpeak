/* ============================================================
   AUTH — Alpine-компонент страницы входа/регистрации
   ============================================================ */
document.addEventListener('alpine:init', function () {
  Alpine.data('authPage', function () {
    return {
      tab: 'signin',

      signinUsername: '',
      signinPassword: '',
      signinShowPassword: false,
      signinError: '',
      busySignin: false,

      signupUsername: '',
      signupFullName: '',
      signupPassword: '',
      signupShowPassword: false,
      signupError: '',
      busySignup: false,

      get footText() {
        return this.tab === 'signin' ? 'Ещё нет аккаунта?' : 'Уже есть аккаунт?';
      },

      get footAction() {
        return this.tab === 'signin' ? 'Зарегистрироваться' : 'Войти';
      },

      switchTab(name, focus) {
        this.tab = name;
        this.signinError = '';
        this.signupError = '';

        if (focus) {
          this.$nextTick(function () {
            var form = this.$refs[name + 'Form'];
            var input = form && form.querySelector('input');
            if (input) input.focus();
          }.bind(this));
        }
      },

      toggleFoot() {
        this.switchTab(this.tab === 'signin' ? 'signup' : 'signin', true);
      },

      togglePassword(kind) {
        this[kind + 'ShowPassword'] = !this[kind + 'ShowPassword'];
      },

      async submitSignin() {
        if (!this.signinUsername.trim() || !this.signinPassword) {
          this.signinError = 'Заполни юзернейм и пароль';
          return;
        }

        await this.submitAuth('signin', '/api/signin', {
          username: this.signinUsername.trim(),
          password: this.signinPassword
        }, 'С возвращением!');
      },

      async submitSignup() {
        var username = this.signupUsername.trim();
        var fullName = this.signupFullName.trim();

        if (!username || !fullName || !this.signupPassword) {
          this.signupError = 'Заполни юзернейм, полное имя и пароль';
          return;
        }

        /* Клиентская проверка совпадает с ограничениями бэкенда,
           чтобы не ловить 422 от FastAPI. */
        if (username.length < 3) {
          this.signupError = 'Юзернейм: минимум 3 символа';
          return;
        }
        if (username.length > 32) {
          this.signupError = 'Юзернейм: максимум 32 символа';
          return;
        }
        if (this.signupPassword.length < 6) {
          this.signupError = 'Пароль: минимум 6 символов';
          return;
        }

        await this.submitAuth('signup', '/api/signup', {
          username: username,
          full_name: fullName,
          password: this.signupPassword
        }, 'Аккаунт создан. Добро пожаловать!');
      },

      async submitAuth(kind, url, payload, successMsg) {
        this[kind + 'Error'] = '';
        this[kind + 'Busy'] = true;

        try {
          var r = await apiFetch(url, {
            method: 'POST',
            body: JSON.stringify(payload)
          });

          /* Успех: сервер выставил HttpOnly-куку AUTH_TOKEN */
          if (r.ok) {
            this.$store.toast.show('🏆 ' + successMsg);
            this.resetForm(kind);
            /* Небольшая пауза, чтобы пользователь увидел тост, затем на главную */
            setTimeout(function () { window.location.assign('/'); }, 500);
            return;
          }

          this[kind + 'Error'] = extractErrorMessage(r.data, r.status);
        } catch (e) {
          this[kind + 'Error'] = 'Нет связи с сервером. Проверь подключение и попробуй ещё раз.';
        } finally {
          this[kind + 'Busy'] = false;
        }
      },

      resetForm(kind) {
        if (kind === 'signin') {
          this.signinUsername = '';
          this.signinPassword = '';
          this.signinShowPassword = false;
        } else {
          this.signupUsername = '';
          this.signupFullName = '';
          this.signupPassword = '';
          this.signupShowPassword = false;
        }
      }
    };
  });
});
