-- ==========================================
-- VIBE TRADING : SUPABASE SQL SCHEMA
-- ==========================================

-- 1. Table: Profiles
-- Extends the default auth.users table
CREATE TABLE public.profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS for profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update their own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- Trigger to automatically create a profile when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (new.id, new.email, new.raw_user_meta_data->>'full_name');
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- 2. Table: Subscriptions
CREATE TYPE subscription_status AS ENUM ('PENDING', 'ACTIVE', 'INACTIVE');

CREATE TABLE public.subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    plan_name TEXT NOT NULL,
    status subscription_status DEFAULT 'PENDING'::subscription_status NOT NULL,
    payment_proof_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own subscriptions" ON public.subscriptions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own subscriptions" ON public.subscriptions FOR INSERT WITH CHECK (auth.uid() = user_id);
-- Only Admins should update status, so no update policy for normal users.


-- 3. Table: MT5 Accounts
CREATE TABLE public.mt5_accounts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    broker_name TEXT NOT NULL,
    login_id TEXT NOT NULL,
    encrypted_password TEXT NOT NULL,
    server_name TEXT NOT NULL,
    account_type TEXT DEFAULT 'Live' NOT NULL,
    status TEXT DEFAULT 'DISCONNECTED' NOT NULL,
    balance NUMERIC DEFAULT 0,
    equity NUMERIC DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE public.mt5_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own mt5 accounts" ON public.mt5_accounts FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own mt5 accounts" ON public.mt5_accounts FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own mt5 accounts" ON public.mt5_accounts FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own mt5 accounts" ON public.mt5_accounts FOR DELETE USING (auth.uid() = user_id);


-- 4. Table: Trades
CREATE TABLE public.trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    symbol TEXT NOT NULL,
    type TEXT NOT NULL, -- 'BUY' or 'SELL'
    entry NUMERIC NOT NULL,
    sl NUMERIC,
    tp NUMERIC,
    profit NUMERIC DEFAULT 0,
    status TEXT DEFAULT 'OPEN' NOT NULL, -- 'OPEN', 'WON', 'LOST'
    open_time TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    close_time TIMESTAMP WITH TIME ZONE
);

-- Enable RLS
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own trades" ON public.trades FOR SELECT USING (auth.uid() = user_id);
-- Normal users should not insert or update trades (only the Python backend via Service Key should do this).

-- Enable Realtime for trades table
ALTER PUBLICATION supabase_realtime ADD TABLE public.trades;
