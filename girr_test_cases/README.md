# GIRR Test Case Files

|ID|Test Case                                              |Valid XML|Expected Result|
|--|-------------------------------------------------------|---------|---------------|
| 1|Empty File                                             |No       |Reject File    |
| 2|Text File                                              |No       |Reject File    |
| 3|No Command elements in File                            |Yes      |Reject File    |
| 4|Name Attribute Missing from Command                    |Yes      |Reject File    |
| 5|Name Attribute Empty but Present in Command            |Yes      |Reject File    |
| 6|Pronto Codes Not Present for command, variant 1        |Yes      |Reject File    |
| 7|Pronto Codes Not Present for command, variant 2        |Yes      |Reject File    |
| 8|Pronto Codes Present for command but Invalid, variant 1|Yes      |Reject File    |
| 9|Pronto Codes Present for command but Invalid, variant 2|Yes      |Reject File    |
|10|Pronto Codes Present for command but Invalid, variant 3|Yes      |Reject File    |
|11|Invalid XML Syntax                                     |No       |Reject File    |
|12|Commands have Duplicate Names                          |Yes      |Reject File    |
|13|More than one Pronto code present for command          |Yes      |Reject File    |
|14|Pronto Code too long per headers                       |Yes      |Reject File    |
|15|Good Sample (small)                                    |Yes      |**Accept** File|
