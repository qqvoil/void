const targetButtons = document.querySelectorAll("[data-target]");
const topMark = document.getElementById("topMark");
const heroLogo = document.getElementById("heroLogo");
const plansSection = document.getElementById("plans");
const entrySection = document.getElementById("entry");

const voidSite = document.getElementById("voidSite");
const landingMenu = document.getElementById("landingMenu");
const menuTrigger = document.getElementById("menuTrigger");
const menuOverlay = document.getElementById("menuOverlay");
const menuLinks = document.querySelectorAll(".menu-overlay__link");

targetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const target = document.querySelector(button.dataset.target);
    if (target) {
      smoothScrollTo(target, 1600);
    }
  });
});

function clamp(value, min, max) {
  return Math.max(min, Math.min(value, max));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function easeInOutCubic(t) {
  return t < 0.5
    ? 4 * t * t * t
    : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function smoothScrollTo(element, duration = 1600) {
  const start = window.pageYOffset;
  const targetY = element.getBoundingClientRect().top + window.pageYOffset;
  const distance = targetY - start;
  const startTime = performance.now();

  function step(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = easeInOutCubic(progress);

    window.scrollTo(0, start + distance * eased);

    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}

function updateMenuAnchor() {
  if (!menuTrigger || !menuOverlay) return;

  const rect = menuTrigger.getBoundingClientRect();
  const anchorX = rect.left + rect.width / 2;
  const anchorTop = rect.bottom + 18;

  menuOverlay.style.setProperty("--menu-anchor-x", `${anchorX}px`);
  menuOverlay.style.setProperty("--menu-anchor-top", `${anchorTop}px`);
}

function setMenuOpen(isOpen) {
  if (!landingMenu || !menuTrigger || !menuOverlay || !voidSite) {
    return;
  }

  if (isOpen) {
    updateMenuAnchor();
  }

  landingMenu.classList.toggle("is-open", isOpen);
  voidSite.classList.toggle("menu-open", isOpen);
  document.body.classList.toggle("menu-open", isOpen);
  menuOverlay.classList.toggle("is-open", isOpen);

  menuTrigger.setAttribute("aria-expanded", String(isOpen));
  menuOverlay.setAttribute("aria-hidden", String(!isOpen));
}

if (menuTrigger) {
  menuTrigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = !landingMenu.classList.contains("is-open");
    setMenuOpen(willOpen);
  });
}

if (menuOverlay) {
  menuOverlay.addEventListener("click", (event) => {
    if (event.target === menuOverlay) {
      setMenuOpen(false);
    }
  });
}

menuLinks.forEach((link) => {
  link.addEventListener("click", () => {
    setMenuOpen(false);
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setMenuOpen(false);
  }
});

window.addEventListener("resize", () => {
  updateMenuAnchor();
});

let smoothY = window.scrollY;

function animate() {
  const realY = window.scrollY;
  smoothY += (realY - smoothY) * 0.065;

  const vh = window.innerHeight || 1;
  const vw = window.innerWidth || 1;
  const edge = vw <= 900 ? 16 : 24;

  const progress = Math.min(smoothY / (vh * 0.7), 1);

  if (heroLogo) {
    const scale = 1 - progress * 0.14;
    const opacity = 1 - progress * 1.08;
    const blur = progress * 1.2;

    heroLogo.style.transform = `scale(${scale})`;
    heroLogo.style.opacity = `${Math.max(opacity, 0)}`;
    heroLogo.style.filter = `
      drop-shadow(0 0 16px rgba(255,255,255,0.08))
      drop-shadow(0 0 44px rgba(255,255,255,0.05))
      blur(${blur}px)
    `;
  }

  if (landingMenu && topMark && plansSection && entrySection) {
    const menuWidth = landingMenu.offsetWidth;
    const markWidth = topMark.offsetWidth;

    const menuCenterX = vw / 2 - menuWidth / 2;
    const menuRightX = vw - edge - menuWidth;

    const markCenterX = vw / 2 - markWidth / 2;
    const markLeftX = edge;

    const toPlans = clamp(
      (smoothY - (plansSection.offsetTop - vh * 0.72)) / (vh * 0.42),
      0,
      1
    );

    const toEntry = clamp(
      (smoothY - (entrySection.offsetTop - vh * 0.62)) / (vh * 0.36),
      0,
      1
    );

    const menuX = lerp(menuCenterX, menuRightX, toPlans);
    const menuOpacity = 1 - toEntry;

    const markPhaseX = lerp(markCenterX, markLeftX, toPlans);
    const markX = lerp(markPhaseX, markCenterX, toEntry);
    const markOpacity = Math.max(toPlans, toEntry);

    landingMenu.style.transform = `translate3d(${menuX}px, 0, 0)`;
    landingMenu.style.opacity = `${menuOpacity}`;
    landingMenu.style.pointerEvents = menuOpacity < 0.08 ? "none" : "auto";

    topMark.style.transform = `translate3d(${markX}px, 0, 0)`;
    topMark.style.opacity = `${markOpacity}`;

    if (menuOpacity < 0.08) {
      setMenuOpen(false);
    }
  }

  if (landingMenu?.classList.contains("is-open")) {
    updateMenuAnchor();
  }

  requestAnimationFrame(animate);
}

requestAnimationFrame(animate);
