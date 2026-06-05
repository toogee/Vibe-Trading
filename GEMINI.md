# Vibe Trading - Documentation Projet & Mémoire IA

## 1. Description de l'Application
**Vibe Trading** est une plateforme SaaS (Software as a Service) et un tableau de bord (Dashboard) pour un système de trading automatisé Forex (Bot de Trading), spécialisé sur la paire GBPUSD et optimisé pour la session de Londres. L'objectif est d'offrir une interface premium, moderne et en français pour les utilisateurs souhaitant suivre les performances de l'IA (baptisée **SSED V2**), souscrire à des plans, et gérer leur compte de trading en temps réel.

## 2. Fonctionnalités Implémentées
- **Landing Page (`index.html`)** : Présentation du bot, de ses avantages, de son fonctionnement et des tarifs. Design "Light Mode" avec animations au défilement et effets de particules.
- **Tableau de Bord (`dashboard.html`)** : Interface principale de l'utilisateur. Design "Ultra Dark Mode" premium avec glassmorphism, effets de lueur néon et disposition adaptative (responsive).
  - Intégration du **widget avancé TradingView** en temps réel pour GBPUSD (5m timeframe).
  - Cartes de métriques de performance (Statut du Bot, Profit Total, Taux de réussite, Drawdown Max).
  - Historique des transactions récentes et liste des positions ouvertes.
  - Section d'abonnement (Starter, Pro, VIP Elite) avec affichage et conversion dynamique en Gourdes Haïtiennes (HTG) basé sur le taux de 134 HTG pour 1 USD.
- **Guide de Démarrage (`guide.html`)** : Guide interactif et bilingue (Français/Kreyòl) expliquant étape par étape l'inscription chez le broker avec lien partenaire, la vérification KYC, la création de compte MT5, le dépôt minimal de 20 USD, la connexion au tableau de bord, et l'activation du bot SSED V2.
- **Authentification (`login.html`, `signup.html`)** : Pages de connexion et d'inscription modernes, rapides et responsives.
- **Traduction Complète** : L'ensemble de la plateforme (Landing Page, Dashboard, menus, modales d'alerte) a été traduit et adapté en français.
- **Interactivité** : Gestion du menu latéral, des onglets, des modales (ex: configuration MT5, abonnements), et alertes interactives (profil utilisateur, modes d'apparence).

## 3. Structure des Fichiers
- `index.html` : Landing page publique (Vitrine).
- `dashboard.html` : Tableau de bord utilisateur (Interface privée et connectée).
- `guide.html` : Page explicative et guide de démarrage bilingue (Français/Kreyòl).
- `login.html` : Page de connexion.
- `signup.html` : Page de création de compte.
- `style.css` : Fichier CSS global gérant le design system (variables), les animations, le mode clair de la landing page et le dark mode ultra-premium du dashboard.
- `script.js` : Logique JavaScript pour les interactions front-end (particules, menu mobile, modales, interactions de base).
- `GEMINI.md` : Ce fichier de documentation agissant comme mémoire de projet pour le contexte IA.

## 4. Technologies Utilisées
- **Front-end** : HTML5 sémantique, CSS3 (Vanilla), JavaScript (Vanilla ES6+).
- **Design & Layout** : Flexbox et Grid CSS. L'approche CSS est hybride, utilisant des classes utilitaires personnalisées (similaires à Tailwind CSS) implémentées en Vanilla CSS pour plus de flexibilité et de contrôle sans dépendances lourdes.
- **Icônes** : Lucide Icons (générées via script JS dans le DOM) pour le Dashboard, et FontAwesome pour la landing page.
- **Graphiques & Données** : API du widget TradingView (pour les données en direct du marché Forex GBPUSD).
- **Animations** : CSS Transitions, CSS Keyframes, effets Glassmorphism (backdrop-filter: blur) et effets de lumière radiale (glow).

## 5. Décisions de Design (UI/UX)
- **Dashboard "Premium Fintech"** : Choix délibéré d'un thème très sombre (Dark Mode exclusif) avec des dégradés bleu marine, des touches de lueur néon bleu/violet (sky-400 / purple-500) et des cartes semi-transparentes (Glassmorphism) pour donner une impression "IA futuriste", professionnelle et technologique.
- **Landing Page "Clean & Trust"** : Thème clair avec des formes fluides et des particules en arrière-plan pour inspirer confiance et clarté aux nouveaux visiteurs.
- **Responsive Design** : Toutes les pages sont conçues pour s'adapter parfaitement aux écrans mobiles (menus hamburgers, adaptation des marges, empilement des grilles). Les problèmes de chevauchement de la barre de navigation sur mobile ont été explicitement corrigés via des media queries CSS.

## 6. Discussions & Développements Futurs (Pour la prochaine IA)
- **Modes de Paiement Locaux** : Les modales de paiement devront être connectées aux API de **Moncash** et **Natcash** pour permettre aux utilisateurs de payer directement avec leur portefeuille mobile local. L'UI du modal de paiement a été évoquée pour offrir explicitement ce choix.
- **Light Mode Dashboard** : Un bouton "Mode Clair" est présent dans les paramètres d'apparence du Dashboard, mais est actuellement désactivé (il affiche une alerte d'indisponibilité temporaire). Le Dashboard a été créé avec une identité visuelle "Dark" très ancrée ; la création d'un vrai thème clair nécessitera une refonte des variables CSS de luminosité.
- **Intégration Backend (API / Base de données)** : Le projet est actuellement statique (Front-end). Il faudra remplacer les données codées en dur (hardcoded) par des appels API réels vers le backend de l'application (Node.js/Python/PHP) pour récupérer :
  - L'état de marche réel du bot SSED V2.
  - L'historique des trades MT5 de l'utilisateur.
  - Le statut de l'abonnement depuis la base de données.
- **MT5 Connection** : La modale "MT5 Settings" devra être branchée à l'API MetaTrader / Manager API pour associer techniquement le compte MetaTrader 5 du client au serveur de trading Vibe Trading.
