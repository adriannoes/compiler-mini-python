#[inline(never)]
fn next(value: i64) -> i64 {
    value + 1
}

#[inline(never)]
fn sum_next(limit: i64) -> i64 {
    let mut index = 0;
    let mut total = 0;
    while index < limit {
        total += next(index);
        index += 1;
    }
    total
}

fn main() {
    let arguments: Vec<String> = std::env::args().collect();
    let limit = if arguments.len() == 2 {
        arguments[1].parse::<i64>().ok().filter(|value| (-2..=8).contains(value))
    } else {
        None
    };
    match limit {
        Some(value) => println!("{}", sum_next(value)),
        None => {
            eprintln!("Supply one integer limit from -2 through 8.");
            std::process::exit(1);
        }
    }
}
