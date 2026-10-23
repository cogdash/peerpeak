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
