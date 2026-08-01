class ArabicTextNormalizer {
  const ArabicTextNormalizer();

  static const _months = <String>[
    '',
    'يناير',
    'فبراير',
    'مارس',
    'أبريل',
    'مايو',
    'يونيو',
    'يوليو',
    'أغسطس',
    'سبتمبر',
    'أكتوبر',
    'نوفمبر',
    'ديسمبر',
  ];

  static const _digitWords = <String>[
    'صفر',
    'واحد',
    'اثنان',
    'ثلاثة',
    'أربعة',
    'خمسة',
    'ستة',
    'سبعة',
    'ثمانية',
    'تسعة',
  ];

  String normalize(String input) {
    var text = _westernDigits(input);
    final protected = <String>[];

    String protect(String value) {
      final token = String.fromCharCode(0xE000 + protected.length);
      protected.add(value);
      return token;
    }

    text = text.replaceAllMapped(
      RegExp(r'\b(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})\b'),
      (match) {
        final day = int.parse(match.group(1)!);
        final month = int.parse(match.group(2)!);
        final year = int.parse(match.group(3)!);
        if (day < 1 || day > 31 || month < 1 || month > 12) {
          return match.group(0)!;
        }
        return protect(
          '${integerToWords(day)} من ${_months[month]} سنة ${integerToWords(year)}',
        );
      },
    );
    text = text.replaceAllMapped(RegExp(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'), (
      match,
    ) {
      final year = int.parse(match.group(1)!);
      final month = int.parse(match.group(2)!);
      final day = int.parse(match.group(3)!);
      if (day < 1 || day > 31 || month < 1 || month > 12) {
        return match.group(0)!;
      }
      return protect(
        '${integerToWords(day)} من ${_months[month]} سنة ${integerToWords(year)}',
      );
    });
    text = text.replaceAllMapped(
      RegExp(
        r'(\d+(?:[\.,]\d+)?)\s*(ر\.?\s?س\.?|SAR|USD|AED|\$|ريال(?:اً)?|دولار|درهم)',
        caseSensitive: false,
      ),
      (match) => protect(
        '${numberToWords(match.group(1)!)} ${_currencyName(match.group(2)!)}',
      ),
    );
    text = text.replaceAllMapped(
      RegExp(r'\d+(?:[\.,]\d+)?'),
      (match) => numberToWords(match.group(0)!),
    );
    for (var index = 0; index < protected.length; index++) {
      text = text.replaceAll(
        String.fromCharCode(0xE000 + index),
        protected[index],
      );
    }
    return text;
  }

  String numberToWords(String value) {
    final normalized = value.replaceAll(',', '.');
    final parts = normalized.split('.');
    final integer = int.tryParse(parts.first);
    if (integer == null) return value;
    final output = StringBuffer(integerToWords(integer));
    if (parts.length > 1 && parts[1].isNotEmpty) {
      output.write(' فاصلة ');
      output.write(
        parts[1]
            .split('')
            .map((digit) => _digitWords[int.parse(digit)])
            .join(' '),
      );
    }
    return output.toString();
  }

  String integerToWords(int value) {
    if (value == 0) return _digitWords.first;
    if (value < 0) return 'سالب ${integerToWords(-value)}';
    if (value > 999999999999999) {
      return value
          .toString()
          .split('')
          .map((digit) => _digitWords[int.parse(digit)])
          .join(' ');
    }
    final groups = <String>[];
    var remaining = value;
    const scales = <({int value, String singular, String dual, String plural})>[
      (
        value: 1000000000000,
        singular: 'تريليون',
        dual: 'تريليونان',
        plural: 'تريليونات',
      ),
      (
        value: 1000000000,
        singular: 'مليار',
        dual: 'ملياران',
        plural: 'مليارات',
      ),
      (value: 1000000, singular: 'مليون', dual: 'مليونان', plural: 'ملايين'),
      (value: 1000, singular: 'ألف', dual: 'ألفان', plural: 'آلاف'),
    ];
    for (final scale in scales) {
      final count = remaining ~/ scale.value;
      if (count == 0) continue;
      groups.add(switch (count) {
        1 => scale.singular,
        2 => scale.dual,
        >= 3 && <= 10 => '${_underThousand(count)} ${scale.plural}',
        _ => '${_underThousand(count)} ${scale.singular}',
      });
      remaining %= scale.value;
    }
    if (remaining > 0) groups.add(_underThousand(remaining));
    return groups.join(' و');
  }

  String _underThousand(int value) {
    const units = <String>[
      '',
      'واحد',
      'اثنان',
      'ثلاثة',
      'أربعة',
      'خمسة',
      'ستة',
      'سبعة',
      'ثمانية',
      'تسعة',
    ];
    const teens = <String>[
      'عشرة',
      'أحد عشر',
      'اثنا عشر',
      'ثلاثة عشر',
      'أربعة عشر',
      'خمسة عشر',
      'ستة عشر',
      'سبعة عشر',
      'ثمانية عشر',
      'تسعة عشر',
    ];
    const tens = <String>[
      '',
      'عشرة',
      'عشرون',
      'ثلاثون',
      'أربعون',
      'خمسون',
      'ستون',
      'سبعون',
      'ثمانون',
      'تسعون',
    ];
    const hundreds = <String>[
      '',
      'مائة',
      'مائتان',
      'ثلاثمائة',
      'أربعمائة',
      'خمسمائة',
      'ستمائة',
      'سبعمائة',
      'ثمانمائة',
      'تسعمائة',
    ];
    final parts = <String>[];
    final hundred = value ~/ 100;
    final rest = value % 100;
    if (hundred > 0) parts.add(hundreds[hundred]);
    if (rest >= 10 && rest < 20) {
      parts.add(teens[rest - 10]);
    } else if (rest > 0) {
      final unit = rest % 10;
      final ten = rest ~/ 10;
      if (unit > 0 && ten > 0) {
        parts.add('${units[unit]} و${tens[ten]}');
      } else if (unit > 0) {
        parts.add(units[unit]);
      } else {
        parts.add(tens[ten]);
      }
    }
    return parts.join(' و');
  }

  String _westernDigits(String value) => value
      .replaceAll('٠', '0')
      .replaceAll('١', '1')
      .replaceAll('٢', '2')
      .replaceAll('٣', '3')
      .replaceAll('٤', '4')
      .replaceAll('٥', '5')
      .replaceAll('٦', '6')
      .replaceAll('٧', '7')
      .replaceAll('٨', '8')
      .replaceAll('٩', '9');

  String _currencyName(String value) {
    final currency = value
        .replaceAll('.', '')
        .replaceAll(' ', '')
        .toUpperCase();
    return switch (currency) {
      r'$' || 'USD' || 'دولار' => 'دولارًا',
      'AED' || 'درهم' => 'درهمًا',
      _ => 'ريالًا سعوديًا',
    };
  }
}
