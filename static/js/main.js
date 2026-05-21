// Barber Metric — main.js

(function () {
  'use strict';

  const SIDEBAR_SCROLL_KEY = 'bc_sidebar_scroll';

  // Sidebar toggle (mobile)
  const sidebar = document.getElementById('sidebar');
  const hamburger = document.getElementById('hamburger');
  const overlay = document.getElementById('sidebarOverlay');
  const closeBtn = document.getElementById('sidebarClose');

  function openSidebar() {
    sidebar && sidebar.classList.add('open');
    overlay && overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar && sidebar.classList.remove('open');
    overlay && overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  hamburger && hamburger.addEventListener('click', openSidebar);
  overlay && overlay.addEventListener('click', closeSidebar);
  closeBtn && closeBtn.addEventListener('click', closeSidebar);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSidebar();
  });

  // ── Persistir scroll da sidebar entre páginas ──
  if (sidebar) {
    // Restaurar scroll salvo
    var saved = sessionStorage.getItem(SIDEBAR_SCROLL_KEY);
    if (saved !== null) {
      sidebar.scrollTop = parseInt(saved, 10);
    }

    // Salvar scroll ao clicar em qualquer link da sidebar
    sidebar.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        sessionStorage.setItem(SIDEBAR_SCROLL_KEY, sidebar.scrollTop);
      });
    });

    // Salvar scroll ao fazer submit de forms dentro da sidebar (trocar barbeiro etc.)
    sidebar.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function () {
        sessionStorage.setItem(SIDEBAR_SCROLL_KEY, sidebar.scrollTop);
      });
    });
  }

  // Auto-dismiss toast messages
  document.querySelectorAll('.toast-msg').forEach(function (el) {
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transition = 'opacity .4s ease';
      setTimeout(function () { el.remove(); }, 400);
    }, 4000);
  });

  // ── Persistir scroll da PÁGINA (útil ao deletar/atualizar itens) ──
  const PAGE_SCROLL_KEY = 'bc_page_scroll_pos';
  const PAGE_PATH_KEY = 'bc_page_scroll_path';

  // Restaurar se for a mesma página
  if (sessionStorage.getItem(PAGE_PATH_KEY) === window.location.pathname) {
    var savedPageScroll = sessionStorage.getItem(PAGE_SCROLL_KEY);
    if (savedPageScroll !== null) {
      // Pequeno timeout para garantir que os elementos já renderizaram
      setTimeout(function() {
        window.scrollTo(0, parseInt(savedPageScroll, 10));
      }, 50);
    }
  }
  // Limpar para não aplicar em navegações futuras sem contexto
  sessionStorage.removeItem(PAGE_PATH_KEY);
  sessionStorage.removeItem(PAGE_SCROLL_KEY);

  // Salvar posição antes de sair (via form submit, link de delete, refresh)
  window.addEventListener('beforeunload', function () {
    sessionStorage.setItem(PAGE_PATH_KEY, window.location.pathname);
    sessionStorage.setItem(PAGE_SCROLL_KEY, window.scrollY);
  });

  // ── Toggle Barbeiro Switcher Mobile ──
  const barbeiroSwitcher = document.querySelector('.barbeiro-switcher');
  const barbeiroAtual = document.querySelector('.barbeiro-atual');
  if (barbeiroSwitcher && barbeiroAtual) {
    barbeiroAtual.addEventListener('click', function(e) {
      barbeiroSwitcher.classList.toggle('open');
      e.stopPropagation();
    });
    document.addEventListener('click', function(e) {
      if (!barbeiroSwitcher.contains(e.target)) {
        barbeiroSwitcher.classList.remove('open');
      }
    });
  }

})();

