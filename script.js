document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialiser Particles.js (plus subtil et premium)
    if (typeof particlesJS !== 'undefined') {
        particlesJS('particles-js', {
            "particles": {
                "number": { "value": 40, "density": { "enable": true, "value_area": 900 } },
                "color": { "value": "#0ea5e9" },
                "shape": { "type": "circle" },
                "opacity": { "value": 0.3, "random": true, "anim": { "enable": true, "speed": 0.5, "opacity_min": 0.1, "sync": false } },
                "size": { "value": 3, "random": true },
                "line_linked": { "enable": true, "distance": 150, "color": "#0ea5e9", "opacity": 0.2, "width": 1 },
                "move": { "enable": true, "speed": 1, "direction": "none", "random": true, "straight": false, "out_mode": "out", "bounce": false }
            },
            "interactivity": {
                "detect_on": "window",
                "events": {
                    "onhover": { "enable": true, "mode": "grab" },
                    "onclick": { "enable": true, "mode": "push" },
                    "resize": true
                },
                "modes": {
                    "grab": { "distance": 140, "line_linked": { "opacity": 0.4 } },
                    "push": { "particles_nb": 2 }
                }
            },
            "retina_detect": true
        });
    }

    // 2. Animations au scroll
    const fadeElements = document.querySelectorAll('.fade-in');

    const intersectionObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                // Optional: Stop observing once animated
                // intersectionObserver.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.15,
        rootMargin: "0px 0px -50px 0px"
    });

    fadeElements.forEach(element => {
        intersectionObserver.observe(element);
    });

    // Trigger hero animations immediately
    setTimeout(() => {
        document.querySelectorAll('.hero .fade-in').forEach(el => {
            el.classList.add('visible');
        });
    }, 100);

    // 3. Navbar logic
    const navbar = document.querySelector('header');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 20) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });

    // 4. Mobile Menu Toggle
    const menuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');
    
    if (menuBtn && navLinks) {
        menuBtn.addEventListener('click', () => {
            navLinks.classList.toggle('active');
        });
        
        // Close menu when clicking a link
        navLinks.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navLinks.classList.remove('active');
            });
        });
    }

    // 5. Redirection dynamique si l'utilisateur est déjà connecté
    if (window.supabaseClient) {
        window.supabaseClient.auth.getSession().then(({ data: { session } }) => {
            if (session && session.user) {
                // Remplacer tous les liens vers signup.html par dashboard.html
                const ctaLinks = document.querySelectorAll('a[href="signup.html"]');
                ctaLinks.forEach(link => {
                    link.href = 'dashboard.html';
                    
                    // Modifier également le texte pour être plus cohérent
                    const text = link.textContent.trim();
                    if (text === 'Commencer Maintenant') {
                        link.textContent = 'Accéder au Tableau de Bord';
                    } else if (text === 'S\'abonner Maintenant' || text === 'Obtenir l\'Offre Pro' || text === 'Devenir VIP') {
                        link.textContent = 'Accéder au Tableau de Bord';
                    }
                });
            }
        }).catch(err => console.error("Erreur vérification session:", err));
    }
});
