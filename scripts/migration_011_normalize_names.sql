-- Comparaison de noms insensible aux accents et aux ligatures.
--
-- Pourquoi : les noms français de la base viennent des impressions Scryfall et
-- ne sont pas homogènes — l'île de base y est « Ile » sans accent, Nécropède
-- avec, et « Nuée de fÆries » porte une ligature là où « Annonciatrice faerie »
-- n'en a pas. Une decklist collée avec l'orthographe correcte ne trouvait donc
-- pas sa carte, partait au repli flou, et s'y voyait proposer la mauvaise
-- (« Île » -> « Île souillée »). L'orthographe qui marche changeait d'une carte
-- à l'autre, sans que rien ne permette de la deviner.
--
-- Une seule implémentation, en SQL, appliquée aux deux côtés de la comparaison :
-- une version Python côté requête aurait fini par diverger de celle-ci.
--
-- `IMMUTABLE` : la fonction ne dépend que de son argument, ce qui la rend
-- indexable si le besoin s'en fait sentir. Aujourd'hui elle ne sert qu'au
-- troisième passage de la résolution, sur le reliquat, donc un balayage suffit.
CREATE OR REPLACE FUNCTION normalize_card_name(card_name TEXT) RETURNS TEXT AS $$
    SELECT lower(
        translate(
            -- Les ligatures valent deux lettres : `translate` ne sait pas le
            -- faire (il substitue caractère par caractère), d'où les `replace`.
            replace(replace(replace(replace(replace(replace(card_name,
                'æ', 'ae'), 'Æ', 'Ae'), 'œ', 'oe'), 'Œ', 'Oe'), 'ﬁ', 'fi'), 'ﬂ', 'fl'),
            'àáâãäåÀÁÂÃÄÅçÇðèéêëÈÉÊËìíîïÌÍÎÏñÑòóôõöøÒÓÔÕÖØùúûüÙÚÛÜýÿÝ',
            'aaaaaaAAAAAAcCdeeeeEEEEiiiiIIIInNooooooOOOOOOuuuuUUUUyyY')
    )
$$ LANGUAGE SQL IMMUTABLE STRICT;
