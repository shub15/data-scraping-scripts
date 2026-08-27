USE Rfam;

-- a) How many types of Acacia plants can be found in the `taxonomy` table of the dataset?
SELECT COUNT(*) AS acacia_count
FROM taxonomy
WHERE species LIKE 'Acacia %';

-- b) Which type of wheat has the longest DNA sequence?
SELECT
    tx.species,
    MAX(rf.length) AS longest_sequence
FROM rfamseq rf
JOIN taxonomy tx ON rf.ncbi_id = tx.ncbi_id
WHERE tx.species LIKE '%wheat%'
   OR tx.species LIKE '%Triticum%'
GROUP BY tx.species
ORDER BY longest_sequence DESC
LIMIT 1;

-- c) Paginated query - 9th page, 15 results per page
SELECT
    f.rfam_acc       AS family_accession,
    f.rfam_id        AS family_name,
    MAX(rf.length)   AS max_sequence_length
FROM family f
JOIN full_region fr ON f.rfam_acc = fr.rfam_acc
JOIN rfamseq rf     ON fr.rfamseq_acc = rf.rfamseq_acc
GROUP BY
    f.rfam_acc,
    f.rfam_id
HAVING MAX(rf.length) > 1000000
ORDER BY max_sequence_length DESC
LIMIT 15 OFFSET 120;