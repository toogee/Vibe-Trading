// Importation et configuration de Supabase
const supabaseUrl = 'https://mzybdzidwyoepwnzjrfy.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16eWJkemlkd3lvZXB3bnpqcmZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAwMjAzMzMsImV4cCI6MjA5NTU5NjMzM30.7EKpMeJFyyu4q-uhdH7i8402J-sRaUrVtTe3o2Vz_D8';

// Initialisation du client Supabase
// (Nous utilisons le client global ajouté via CDN dans les fichiers HTML)
window.supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey);

// Vous pouvez utiliser 'supabase' pour faire des requêtes depuis les autres scripts
console.log('✅ Supabase connecté avec succès !');
