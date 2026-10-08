(function () {
  function initMobileNav() {
    var header = document.querySelector('.site-header');
    var wrap = header && header.querySelector('.nav-wrap');
    var nav = wrap && wrap.querySelector('.nav');
    if (!header || !wrap || !nav || wrap.querySelector('.nav-toggle')) return;

    if (!nav.id) nav.id = 'site-navigation';

    var lang = (document.documentElement.lang || 'en').toLowerCase();
    var label = lang.indexOf('fr') === 0 ? 'Ouvrir le menu' : 'Open menu';
    var closeLabel = lang.indexOf('fr') === 0 ? 'Fermer le menu' : 'Close menu';

    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'nav-toggle';
    button.setAttribute('aria-controls', nav.id);
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', label);
    button.innerHTML = '<span class="nav-toggle-bar"></span><span class="nav-toggle-bar"></span><span class="nav-toggle-bar"></span>';
    wrap.insertBefore(button, nav);

    function setOpen(open) {
      nav.classList.toggle('is-open', open);
      header.classList.toggle('nav-open', open);
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      button.setAttribute('aria-label', open ? closeLabel : label);
    }

    button.addEventListener('click', function () {
      setOpen(!nav.classList.contains('is-open'));
    });

    nav.addEventListener('click', function (event) {
      if (event.target.closest('a') && window.matchMedia('(max-width: 760px)').matches) setOpen(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setOpen(false);
    });

    document.addEventListener('click', function (event) {
      if (window.matchMedia('(max-width: 760px)').matches && nav.classList.contains('is-open') && !header.contains(event.target)) setOpen(false);
    });

    window.addEventListener('resize', function () {
      if (!window.matchMedia('(max-width: 760px)').matches) setOpen(false);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMobileNav);
  } else {
    initMobileNav();
  }
})();
